"""Pure Python CTA rules for active-property sales timeline and budget control."""
from __future__ import annotations
from datetime import date
from typing import Any
from .utils import to_float


def assess_project_alerts(*, today: date, target_sale_date: date | None, is_sold: bool, budget_total: float, projected_completion: float, near_budget_pct: float = 85.0) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []
    days_overdue = 0
    if not is_sold and target_sale_date:
        days_overdue = (today - target_sale_date).days
        if days_overdue > 0:
            alerts.append({"type": "sales_overdue", "severity": "critical", "days": days_overdue,
                           "title": f"Target penjualan terlewati {days_overdue} hari",
                           "action": "Periksa ulang harga terhadap listing terbaru, kualitas foto dan deskripsi, status dokumen, kecepatan respons calon pembeli, kanal pemasaran, serta kebutuhan agen. Jangan menurunkan harga tanpa memperbarui analisis pasar."})
        elif days_overdue >= -14:
            alerts.append({"type": "sales_due_soon", "severity": "warning", "days_remaining": abs(days_overdue),
                           "title": f"Target penjualan tinggal {abs(days_overdue)} hari",
                           "action": "Pastikan listing aktif, dokumentasi siap, harga kompetitif dan tindak lanjut calon pembeli terjadwal."})
    budget_total = max(0.0, to_float(budget_total)); projected_completion = max(0.0, to_float(projected_completion))
    if budget_total > 0:
        ratio = projected_completion / budget_total * 100.0
        delta_favorable = budget_total - projected_completion
        if ratio >= 100:
            alerts.append({"type": "budget_overrun", "severity": "critical", "ratio_pct": ratio,
                           "delta_budget_minus_forecast": delta_favorable,
                           "title": f"Proyeksi biaya melewati budget sebesar Rp{abs(delta_favorable):,.0f}",
                           "action": "Tahan pekerjaan tambahan yang belum disetujui, periksa item penyebab selisih, rekonsiliasi transaksi yang belum tertaut, minta penawaran revisi dan setujui perubahan budget secara eksplisit."})
        elif ratio >= near_budget_pct:
            alerts.append({"type": "budget_near_limit", "severity": "warning", "ratio_pct": ratio,
                           "delta_budget_minus_forecast": delta_favorable,
                           "title": f"Proyeksi biaya sudah {ratio:.1f}% dari budget",
                           "action": "Tinjau sisa pekerjaan, komitmen belum dibayar dan forecast. Minta persetujuan untuk pekerjaan tambah sebelum membuat komitmen baru."})
        elif ratio >= 70:
            alerts.append({"type": "budget_monitor", "severity": "info", "ratio_pct": ratio,
                           "delta_budget_minus_forecast": delta_favorable,
                           "title": f"Realisasi proyeksi menggunakan {ratio:.1f}% dari budget",
                           "action": "Lanjutkan pemantauan dan pastikan seluruh aktual, komitmen, dan forecast diperbarui."})
    return {"alerts": alerts, "budget_usage_pct": projected_completion / budget_total * 100 if budget_total > 0 else None,
            "budget_remaining": budget_total - projected_completion if budget_total > 0 else None,
            "days_overdue": days_overdue}
