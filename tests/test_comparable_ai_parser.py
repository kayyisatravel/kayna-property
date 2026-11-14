import json
from datetime import date

import services.gemini_parser as gp
from core.market_engine import assess_comparables

SAMPLE_AI_RESULT = {
    "items": [
        {"name":"Rumah Hook Siap Huni (Lingkar Timur)","address":"Kawasan Perumahan Alam Mutiara, Desa Kendalpecabean, Candi, Sidoarjo 61271","complex_name":"Alam Mutiara","price":550000000,"land_area":123,"building_area":100,"bedrooms":2,"bathrooms":2,"condition":"Siap Huni","condition_detail":"Hook dekat Jalan Lingkar Timur","access":None,"certificate":"SHM","orientation":"Barat","electricity_watt":1300,"water_source":None,"source_platforms":["Rumah123","OLX Indonesia"],"source_evidence":"Dipromosikan agen melalui Rumah123 dan OLX Indonesia","source_url":None,"listing_date":None,"price_type":"Asking aktif","notes":"Nomor blok dirahasiakan agen."},
        {"name":"Rumah Minimalis Full Renovasi","address":"Perumahan Alam Mutiara, Desa Kendalpecabean, Candi, Sidoarjo 61271","complex_name":"Alam Mutiara","price":485000000,"land_area":120,"building_area":100,"bedrooms":2,"bathrooms":1,"condition":None,"condition_detail":"Full renovasi menurut listing","access":None,"certificate":"SHM","orientation":None,"electricity_watt":1300,"water_source":"PDAM Umbulan","source_platforms":["Pinhome","Brighton Real Estate"],"source_evidence":"Tersedia di portal Pinhome dan Brighton Real Estate","source_url":None,"listing_date":None,"price_type":"Asking aktif","notes":"Dimensi tanah 8 x 15 m; KPR tersedia."},
        {"name":"Rumah 1 Lantai 3 Kamar Tidur","address":"Perum Alam Mutiara, Desa Kendalpecabean, Candi, Sidoarjo 61271","complex_name":"Alam Mutiara","price":450000000,"land_area":90,"building_area":36,"bedrooms":3,"bathrooms":1,"condition":None,"condition_detail":None,"access":None,"certificate":"SHM","orientation":"Timur","electricity_watt":1300,"water_source":"PDAM","source_platforms":["Brighton Real Estate"],"source_evidence":"Listing aktif pada Brighton Real Estate","source_url":None,"listing_date":None,"price_type":"Asking aktif","notes":"Dimensi tanah 6 x 15 m; harga nego."},
        {"name":"Rumah Sekunder Blok B4 No. 6","address":"Perumahan Alam Mutiara Blok B4 No. 6, Desa Kendalpecabean, Candi, Sidoarjo 61271","complex_name":"Alam Mutiara","price":350000000,"land_area":135,"building_area":None,"bedrooms":2,"bathrooms":None,"condition":"Siap Huni","condition_detail":"Siap huni menurut listing","access":None,"certificate":None,"orientation":None,"electricity_watt":None,"water_source":None,"source_platforms":["Pinhome"],"source_evidence":"Dip offer melalui Pinhome; disebut legalitas aman dan KPR tersedia","source_url":None,"listing_date":None,"price_type":"Asking aktif","notes":"LB tidak disebutkan; jangan ditebak."},
        {"name":"Rumah Luas Tanah 137 m2 (Kode KSZ 181)","address":"Perum Alam Mutiara, Desa Kendalpecabean, Candi, Sidoarjo 61271","complex_name":"Alam Mutiara","price":350000000,"land_area":137,"building_area":36,"bedrooms":2,"bathrooms":1,"condition":None,"condition_detail":None,"access":None,"certificate":"SHM","orientation":"Selatan","electricity_watt":1300,"water_source":"Sumur","source_platforms":["Dot Property Indonesia"],"source_evidence":"Dipublikasikan agen Galaxy Zeven pada Dot Property Indonesia","source_url":None,"listing_date":None,"price_type":"Asking aktif","notes":"Kode listing KSZ 181; dimensi 9 x 15,2 m; satu carport."}
    ],
    "parsing_notes": ["Tidak ada URL langsung atau tanggal publikasi dalam teks; keduanya dibiarkan kosong."]
}


def _has_additional_properties(node):
    if isinstance(node, dict):
        if "additionalProperties" in node:
            return True
        return any(_has_additional_properties(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_additional_properties(v) for v in node)
    return False


def test_gemini_schemas_do_not_emit_additional_properties():
    assert not _has_additional_properties(gp.AuctionExtraction.model_json_schema())
    assert not _has_additional_properties(gp.ComparableExtraction.model_json_schema())


def test_ai_comparable_parser_keeps_one_record_per_numbered_listing(monkeypatch):
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(SAMPLE_AI_RESULT, ensure_ascii=False))
    text = "1. Rumah satu\n• Alamat\n• Harga\n2. Rumah dua\n• Alamat\n• Harga\n3. Rumah tiga\n• Alamat\n• Harga\n4. Rumah empat\n• Alamat\n• Harga\n5. Rumah lima\n• Alamat\n• Harga"
    parsed = gp.parse_comparable_narrative("fake-key", text)
    assert parsed["count"] == 5
    assert len(parsed["items"]) == 5
    assert parsed["items"][0]["price"] == 550000000
    assert parsed["items"][3]["building_area"] is None
    assert parsed["items"][0]["source_platforms"] == "Rumah123; OLX Indonesia"
    assert parsed["items"][0]["source_url"] == ""
    assert parsed["items"][0]["date_found"] == date.today().isoformat()
    assert parsed["items"][0]["listing_date"] is None
    assert parsed["items"][1]["condition"] is None


def test_user_five_listing_example_is_usable_for_preliminary_market_valuation(monkeypatch):
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(SAMPLE_AI_RESULT, ensure_ascii=False))
    narrative = "\n".join([f"{i}. Rumah pembanding {i}\n• Alamat\n• Harga\n• LT/LB\n• Sumber" for i in range(1, 6)])
    parsed = gp.parse_comparable_narrative("fake-key", narrative)
    market = assess_comparables(parsed["items"], {"complex_name":"Alam Mutiara", "land_area":120, "building_area":90})
    assert market["valid_count"] == 5
    assert market["base_exit"] > 0
    assert market["conservative_exit"] < market["base_exit"]
    assert market["direct_url_count"] == 0
    assert market["go_grade_count"] == 0
    assert market["status"] == "PRELIMINARY"
    assert market["confidence"] > 0


def test_numbered_narrative_sections_are_detected_as_five_listings_not_bullet_lines():
    narrative = """1. Rumah Hook Siap Huni (Lingkar Timur)
• Alamat & Posisi. Alam Mutiara, Candi, Sidoarjo.
• Harga Penawaran. Rp 550.000.000.
• Spesifikasi. LT 123 m², LB 100 m², 2 KT, 2 KM.
• Legalitas. SHM.
• Sumber. Rumah123 dan OLX Indonesia.

2. Rumah Minimalis Full Renovasi
• Alamat. Alam Mutiara, Candi, Sidoarjo.
• Harga. Rp 485.000.000.
• Spesifikasi. LT 120 m², LB 100 m².
• Legalitas. SHM.
• Sumber. Pinhome dan Brighton.

3. Rumah 1 Lantai 3 Kamar Tidur
• Harga. Rp 450.000.000.
• Spesifikasi. LT 90 m², LB 36 m².
• Legalitas. SHM.
• Sumber. Brighton.

4. Rumah Sekunder Blok B4 No. 6
• Harga. Rp 350.000.000.
• LT 135 m², siap huni.
• Sumber. Pinhome.

5. Rumah Luas Tanah 137 m² (Kode KSZ 181)
• Harga. Rp 350.000.000.
• LT 137 m², LB 36 m².
• Legalitas. SHM.
• Sumber. Dot Property Indonesia.
"""
    blocks = gp._detect_numbered_listing_sections(narrative)
    assert len(blocks) == 5
    assert "• Sumber. Rumah123 dan OLX Indonesia." in blocks[0]
    assert "• Sumber. Pinhome dan Brighton." in blocks[1]
    assert "• Sumber. Dot Property Indonesia." in blocks[4]


def test_parser_rejects_wrong_number_of_ai_rows_instead_of_loading_fragmented_bullets(monkeypatch):
    bad_result = {"items": [SAMPLE_AI_RESULT["items"][0]], "parsing_notes": []}
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(bad_result))
    narrative = "1. Listing Satu\n• Alamat\n• Harga\n2. Listing Dua\n• Alamat\n• Harga"
    try:
        gp.parse_comparable_narrative("fake-key", narrative)
        assert False, "Expected mismatched result count to be rejected"
    except RuntimeError as exc:
        assert "mengembalikan 1 baris" in str(exc)


def test_date_found_does_not_fake_listing_freshness():
    from core.market_engine import assess_comparables
    row = SAMPLE_AI_RESULT["items"][0].copy()
    row.update({"source_platforms":"Rumah123", "source_url":"https://example.com/listing", "date_found":date.today().isoformat(), "listing_date":None, "price_type":"Asking aktif"})
    market = assess_comparables([row], {"land_area":123,"building_area":100})
    assert market["valid_count"] == 1
    assert market["valid"][0]["recency_score"] == 35
    assert market["go_grade_count"] == 0  # URL exists, but no individual-listing scope confirmation
    row["source_url_scope"] = "Listing individual"
    market_verified = assess_comparables([row], {"land_area":123,"building_area":100})
    assert market_verified["go_grade_count"] == 1


MARKDOWN_SEVEN_LISTINGS = r"""**1. [Rumah Posisi Hook di Perum TAS 3 (Kepuhkemiri)](https://www.google.com/search?kgmid=%2Fg%2F11w43r0dw3)**
- **Alamat & Posisi.** Perumahan Taman Anggun Sejahtera 3, Desa Kepuhkemiri, Kec. Tulangan, Kab. Sidoarjo 61273.
- **Harga Penawaran.** Rp 550.000.000.
- **Spesifikasi Bangunan.** LT 135 m², 1 lantai, 2 KT, 1 KM.
- **Sumber Listing.** [Trovit Properti](https://rumah.trovit.co.id/taman-anggun-sejahtera-3-sidoarjo).

**2. Rumah Siap Huni Full Renovasi Perum TAS 3 (Hadap Selatan)**
- **Harga Penawaran.** Rp 435.000.000.
- **Spesifikasi Bangunan.** LT 90 m², LB 90 m², 3 KT, 1 KM.
- **Sumber Listing.** [Rumaindo](https://rumaindo.com/iklan/dijual-rumah-siap-huni-perum-tas-3-wonoayu-sidoarjo-ri-964295342).

**3. Rumah Renovasi Atap Galvalum di Perum TAS 3**
- **Harga Penawaran.** Rp 430.000.000.
- **Spesifikasi Bangunan.** LT 90 m², LB 45 m², 3 KT, 1 KM.
- **Sumber Listing.** [Rumah123](https://www.rumah123.com/venue/perumtas-3-vmi35623/).

**4. Rumah SHM Sisa Tanah Belakang di Perum TAS 3 (Kepuhkemiri)**
- **Harga Penawaran.** Rp 350.000.000.
- **Spesifikasi Bangunan.** LT 96 m², LB 42 m², 3 KT, 1 KM.
- **Sumber Listing.** [OLX Indonesia](https://www.olx.co.id/sidoarjo_g5002422/properti_c88/q-taman-anggun-sejahtera) dan Trovit.

**5. Rumah Sekunder Tipe 48/90 di Perumtas 3**
- **Harga Penawaran.** Rp 275.000.000.
- **Spesifikasi Bangunan.** LT 90 m², LB 48 m², 2 KT, 1 KM.
- **Sumber Listing.** Rumah123.

**6. Rumah Luas Tanah 102 m² Row Jalan 7 Meter di Perum TAS 3**
- **Harga Penawaran.** Rp 235.000.000.
- **Spesifikasi Bangunan.** LT 102 m², LB tidak disebutkan, 3 KT, 1 KM.
- **Sumber Listing.** Trovit Properti.

**7. Rumah Asri Siap Huni di Perumtas 3 (Dekat Fasum)**
- **Harga Penawaran.** Rp 575.000.000.
- **Spesifikasi Bangunan.** LT 90 m², LB 69 m², 2 KT, 2 KM.
- **Sumber Listing.** Brighton melalui Rumah123.
"""


def _compact_item(index, price, lt, lb, name=None):
    return {
        "i": index,
        "n": name or f"Listing {index}",
        "a": "Perum TAS 3, Tulangan, Sidoarjo",
        "cx": "TAS 3",
        "p": price,
        "lt": lt,
        "lb": lb,
        "kt": 2,
        "km": 1,
        "c": None,
        "cd": None,
        "ac": None,
        "ad": None,
        "cert": None,
        "ori": None,
        "w": None,
        "water": None,
        "src": ["Rumah123"],
        "dt": None,
        "pt": "Asking aktif",
        "nt": "Data contoh ringkas",
    }


def test_markdown_bold_link_headings_detect_seven_listing_blocks():
    blocks = gp._detect_numbered_listing_sections(MARKDOWN_SEVEN_LISTINGS)
    assert len(blocks) == 7
    assert blocks[0].startswith("**1.")
    assert blocks[6].startswith("**7.")


def test_section_url_extraction_ignores_google_knowledge_panel_and_keeps_portal_url():
    blocks = gp._detect_numbered_listing_sections(MARKDOWN_SEVEN_LISTINGS)
    urls = gp._extract_section_urls(blocks[0])
    assert urls == ["https://rumah.trovit.co.id/taman-anggun-sejahtera-3-sidoarjo"]


def test_seven_listing_narrative_parses_in_two_compact_requests_and_maps_source_urls(monkeypatch):
    calls = []
    prices = [550_000_000, 435_000_000, 430_000_000, 350_000_000, 275_000_000, 235_000_000, 575_000_000]
    land = [135, 90, 90, 96, 90, 102, 90]
    building = [None, 90, 45, 42, 48, None, 69]

    def fake_call(api_key, model, prompt, **kwargs):
        calls.append(kwargs)
        import re
        ids = [int(x) for x in re.findall(r"\[LISTING (\d+)\]", prompt)]
        items = [_compact_item(i, prices[i-1], land[i-1], building[i-1]) for i in ids]
        payload = {"items": items, "parsing_notes": []}
        return {"text": json.dumps(payload, ensure_ascii=False), "finish_reason": "STOP", "output_tokens": 700}

    monkeypatch.setattr(gp, "_client_call", fake_call)
    parsed = gp.parse_comparable_narrative("fake-key", MARKDOWN_SEVEN_LISTINGS)
    assert parsed["count"] == 7
    assert parsed["api_calls"] == 2
    assert len(calls) == 2
    assert parsed["items"][0]["price"] == 550_000_000
    assert parsed["items"][0]["source_url"].startswith("https://rumah.trovit.co.id/")
    assert parsed["items"][1]["source_url"].startswith("https://rumaindo.com/iklan/")
    assert parsed["items"][2]["source_url"].startswith("https://www.rumah123.com/venue/")
    assert parsed["items"][3]["source_url"].startswith("https://www.olx.co.id/")
    assert parsed["items"][0]["source_url_scope"] == "Portal pencarian/kategori"
    assert parsed["items"][1]["source_url_scope"] == "Listing individual"
    assert parsed["items"][2]["source_url_scope"] == "Halaman venue/kompleks"
    assert parsed["items"][3]["source_url_scope"] == "Portal pencarian/kategori"
    assert parsed["items"][4]["source_url"] == ""
    assert parsed["items"][5]["building_area"] is None
    assert parsed["items"][6]["price"] == 575_000_000
    assert "return_metadata" in calls[0]
    assert calls[0]["max_output_tokens"] == 4096


def test_comparable_parser_explains_max_tokens_without_loading_partial_rows(monkeypatch):
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: {
        "text": '{"items":[{"i":1,"n":"incomplete"}',
        "finish_reason": "MAX_TOKENS",
    })
    try:
        gp.parse_comparable_narrative("fake-key", "1. Listing satu\n• Harga 100 juta\n• LT 90 m2")
        assert False, "Expected MAX_TOKENS error"
    except RuntimeError as exc:
        assert "MAX_TOKENS" in str(exc)
        assert "Tidak ada data parsial" in str(exc)


def test_parser_limits_single_free_tier_batch_to_ten_listings():
    narrative = "\n\n".join(f"**{i}. Listing {i}**\n- Harga Rp 100.000.000\n- LT 90 m2" for i in range(1, 12))
    try:
        gp.parse_comparable_narrative("fake-key", narrative)
        assert False, "Expected max ten listing validation"
    except ValueError as exc:
        assert "Maksimal 10 listing" in str(exc)
