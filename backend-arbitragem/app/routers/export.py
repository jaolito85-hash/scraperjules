from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import io
import csv
from typing import List

router = APIRouter(prefix="/export", tags=["export"])


@router.post("/facebook-csv")
async def export_to_facebook(leads: List[dict]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "phone", "fn", "ln", "country"])

    for lead in leads:
        if lead.get("is_revealed") and (lead.get("email") or lead.get("phone")):
            phone = lead.get("phone", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            if len(phone) >= 10 and not phone.startswith("55"):
                phone = f"55{phone}"

            email = lead.get("email", "").lower()
            full_name = lead.get("seller_name", "Cliente")
            name_parts = full_name.split()
            fn = name_parts[0] if name_parts else ""
            ln = name_parts[-1] if len(name_parts) > 1 else ""

            writer.writerow([email, phone, fn, ln, "BR"])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=facebook_audiences_leads.csv"},
    )
