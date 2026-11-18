"""Generate the demo documents for a fictional company, Nilaveli Electronics.

The facts are deliberately spread across files (for example a product's
warranty plan is in the catalog, but what that plan covers is in the policy
PDF), which is the situation where a knowledge graph helps retrieval.

Run:  python scripts/make_sample_docs.py
"""

from pathlib import Path

import docx
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parents[1] / "sample_data"
OUT.mkdir(exist_ok=True)

PROFILE = """# Nilaveli Electronics - Company Profile

## About us
Nilaveli Electronics (Pvt) Ltd is a home appliance and electronics retailer in Sri Lanka. The company was founded in 2009 by Ravindu Perera in Colombo. Today we sell air conditioners, refrigerators, washing machines, televisions and small kitchen appliances under our own brand, Nila, through four branches and our customer care hotline.

## Leadership team
Ishara Fernando is the Chief Executive Officer. Dilani Jayawardena is the Head of Customer Care and handles complaints that cannot be solved at a branch. Mahesh Ratnayake is the Head of After-Sales Service and leads both service centres.

## Branches
### Colombo 03 Flagship Branch
The Colombo 03 Flagship Branch is at 214 Galle Road, Kollupitiya, Colombo 03. Opening hours are Monday to Saturday 9.00 AM - 8.00 PM and Sunday 10.00 AM - 6.00 PM. The branch manager is Kasun Wijesinghe. This branch has a service centre for repairs.

### Kandy Branch
The Kandy Branch is at 45 Dalada Veediya, Kandy. Opening hours are Monday to Saturday 9.00 AM - 7.00 PM. The Kandy Branch is closed on Sundays and public holidays. The branch manager is Tharindu Bandara.

### Galle Branch
The Galle Branch is at 12 Wakwella Road, Galle. Opening hours are Monday to Saturday 9.30 AM - 6.30 PM and Sunday 10.00 AM - 2.00 PM. The branch manager is Shalini de Silva. This branch has a service centre for repairs.

### Kurunegala Branch
The Kurunegala Branch is at 88 Colombo Road, Kurunegala. Opening hours are Monday to Friday 9.00 AM - 6.00 PM and Saturday 9.00 AM - 1.00 PM. The Kurunegala Branch is closed on Sundays. The branch manager is Nadeesha Herath. The Kurunegala Branch is a compact showroom and does not stock air conditioners, but air conditioners can be ordered there for home delivery.

## Contact
Customer care hotline: 011 245 7788 (Monday to Saturday, 8.00 AM - 8.00 PM). Email: care@nilaveli-electronics.example. WhatsApp support is available 24 hours a day through our chatbot.
"""

CATALOG = [
    ("Air Conditioners", [
        ("Nila AirCool 12000 Inverter AC", "NAC-12I", "Rs. 189,900", "Gold Care", "Colombo 03, Kandy, Galle"),
        ("Nila AirCool 18000 Inverter AC", "NAC-18I", "Rs. 264,500", "Gold Care", "Colombo 03, Kandy, Galle"),
    ]),
    ("Refrigerators", [
        ("Nila FrostFree 340L Refrigerator", "NFR-340", "Rs. 154,990", "Silver Care", "All branches"),
        ("Nila DoubleDoor 250L Refrigerator", "NFR-250", "Rs. 112,500", "Silver Care", "All branches"),
    ]),
    ("Washing Machines", [
        ("Nila WashPro 8kg Front Load Washer", "NWM-8F", "Rs. 139,900", "Gold Care", "All branches"),
        ("Nila EasyWash 7kg Top Load Washer", "NWM-7T", "Rs. 86,750", "Silver Care", "All branches"),
    ]),
    ("Televisions", [
        ("Nila VisionMax 55 inch 4K Smart TV", "NTV-55U", "Rs. 229,000", "Silver Care", "Colombo 03, Kandy, Galle"),
        ("Nila VisionMax 43 inch Full HD Smart TV", "NTV-43F", "Rs. 129,500", "Basic Care", "All branches"),
    ]),
    ("Small Appliances", [
        ("Nila PowerBlend 1200W Blender", "NBL-12", "Rs. 18,450", "Basic Care", "All branches"),
        ("Nila RiceMaster 1.8L Rice Cooker", "NRC-18", "Rs. 12,900", "Basic Care", "All branches"),
        ("Nila BreezeLine 16 inch Pedestal Fan", "NPF-16", "Rs. 9,750", "Basic Care", "All branches"),
    ]),
]

POLICIES = [
    ("Warranty plans", [
        "Every Nila product comes with one of three warranty plans: Basic Care, Silver Care or Gold Care. The plan for each product is listed in the product catalog.",
        "Basic Care covers parts and labour for 1 year. Repairs under Basic Care are carry-in: the customer brings the product to a branch.",
        "Silver Care covers parts and labour for 2 years. Refrigerators under Silver Care also get a 5 year warranty on the compressor. Large items under Silver Care are repaired at the customer's home.",
        "Gold Care covers parts and labour for 3 years, with a 10 year warranty on the inverter compressor of air conditioners and on the motor of washing machines. Gold Care includes one free general service in the first year and home-visit repairs.",
        "The warranty does not cover damage from power surges without a surge protector, water damage, physical damage, or repairs done by anyone other than Nilaveli Electronics. Keep your invoice; it is your warranty card.",
    ]),
    ("Repairs and service centres", [
        "Repairs are done at our two service centres, in the Colombo 03 Flagship Branch and the Galle Branch. Products handed in at the Kandy or Kurunegala branches are sent to the Colombo 03 service centre, and repairs then take 7 to 10 working days.",
        "Repairs at a service centre usually take 3 to 5 working days. To book a home-visit repair, call the hotline 011 245 7788.",
    ]),
    ("Returns and exchanges", [
        "Unopened products can be returned within 7 days of purchase for a full refund, with the original invoice.",
        "Opened products can be exchanged within 7 days only if they are faulty. After 7 days, faults are handled under the warranty.",
        "Air conditioners that have already been installed cannot be returned. Refunds are paid to the original payment method within 5 working days.",
    ]),
    ("Delivery and installation", [
        "Delivery is free within the Colombo and Gampaha districts for orders above Rs. 50,000. Smaller orders in the Western Province cost Rs. 2,500 to deliver. Delivery to other provinces costs Rs. 4,500 for any order value.",
        "Deliveries take 2 to 4 working days. Same-day delivery is available in Colombo city for orders placed before 12 noon, for an extra Rs. 1,500.",
        "Air conditioner installation is free within the Colombo and Gampaha districts. Outside these districts installation costs Rs. 7,500.",
    ]),
    ("Payments and instalments", [
        "We accept cash, Visa and Mastercard credit and debit cards, and bank transfers. American Express cards are not accepted. Cheques are not accepted.",
        "0% interest instalment plans for 6 or 12 months are available on Visa and Mastercard credit cards for purchases above Rs. 75,000.",
        "Cash on delivery is available for orders up to Rs. 100,000.",
    ]),
]

FAQ = """# Frequently Asked Questions

Q: Do you sell other brands, such as Samsung or LG?
A: No. Nilaveli Electronics sells only its own Nila brand products.

Q: Can I order online?
A: You can place an order through the customer care hotline 011 245 7788 or on WhatsApp, and pay by bank transfer or cash on delivery. We do not have an online shop yet.

Q: How do I claim my warranty?
A: Bring the product and your invoice to any branch, or call the hotline to book a home visit if your warranty plan includes home-visit repairs.

Q: Is there a loyalty programme?
A: Yes. Nila Rewards members earn 1 point for every Rs. 100 spent. 500 points can be used as Rs. 1,000 off a future purchase. Joining is free at any branch.

Q: Do you buy back old appliances?
A: Yes, we offer an exchange programme for old refrigerators and washing machines of any brand. The trade-in value is decided by a branch technician after inspection, and it is usually between Rs. 5,000 and Rs. 20,000.

Q: Can I get an invoice in my company's name?
A: Yes. Ask the cashier for a VAT invoice and provide your company's VAT registration number.
"""

PROMO_HTML = """<!doctype html>
<html><head><title>Nilaveli Electronics - Year-End Sale 2026</title></head>
<body><main>
<h1>Year-End Sale 2026</h1>
<p>The Nilaveli Electronics Year-End Sale runs from 1 December 2026 to 31 December 2026 at all branches.</p>
<h2>Offers</h2>
<ul>
<li>15% off the Nila WashPro 8kg Front Load Washer during the Year-End Sale.</li>
<li>A free Nila BreezeLine 16 inch Pedestal Fan with every Nila AirCool air conditioner purchased during the sale.</li>
<li>Double Nila Rewards points on all televisions during the Year-End Sale.</li>
</ul>
<h2>Terms</h2>
<p>Offers cannot be combined with other discounts. Offers are valid while stocks last. Instalment plans can be used with sale prices.</p>
</main></body></html>
"""


SPECS = """# Nila Product Specifications

## Nila AirCool 12000 Inverter AC
The Nila AirCool 12000 is a 12,000 BTU split air conditioner suitable for rooms up to 18 square metres. It uses R32 refrigerant and an inverter compressor that adjusts its speed to the room temperature, which saves up to 40% electricity compared with a fixed-speed unit. Noise level is 24 dB on the lowest fan setting. It has a sleep mode, a 24 hour timer and a self-cleaning indoor coil. The unit runs on 230 V single-phase power.

## Nila AirCool 18000 Inverter AC
The Nila AirCool 18000 is an 18,000 BTU split air conditioner for rooms up to 28 square metres or open-plan living areas. Like the 12000 model it uses R32 refrigerant and an inverter compressor. It has a turbo cooling mode that cools a hot room in about 10 minutes, a dust filter that can be washed with water, and Wi-Fi control through the Nila Home app.

## Nila FrostFree 340L Refrigerator
The FrostFree 340L is a two-door refrigerator with a 250 litre fresh food section and a 90 litre freezer on top. Frost-free cooling means the freezer never needs manual defrosting. It has an inverter compressor, toughened glass shelves and a 5 star energy rating. Height is 172 cm and width is 60 cm.

## Nila DoubleDoor 250L Refrigerator
The DoubleDoor 250L is a compact two-door refrigerator for small families, with a 190 litre fresh food section and a 60 litre freezer. It uses direct cooling, so the freezer should be defrosted every few weeks. Height is 150 cm and width is 55 cm.

## Nila WashPro 8kg Front Load Washer
The WashPro 8kg is a front load washing machine with an 8 kg drum, a maximum spin speed of 1400 rpm and 15 wash programmes, including quick wash, wool and baby care. It has a direct-drive inverter motor that is quieter and uses less water than a belt motor. It needs a cold water connection and a drain within 1.5 metres.

## Nila EasyWash 7kg Top Load Washer
The EasyWash 7kg is a fully automatic top load washing machine with a 7 kg drum and 8 wash programmes. It has a child lock and a delay start timer of up to 24 hours. It works with low water pressure, which makes it suitable for homes with an overhead tank.

## Nila VisionMax 55 inch 4K Smart TV
The VisionMax 55 inch has a 4K Ultra HD LED panel with HDR10 support, built-in Wi-Fi, three HDMI ports and two USB ports. It runs the Nila Smart TV platform with YouTube and Netflix apps and supports screen mirroring from Android phones. Speaker output is 2 x 12 W.

## Nila VisionMax 43 inch Full HD Smart TV
The VisionMax 43 inch has a Full HD (1920 x 1080) LED panel, built-in Wi-Fi, two HDMI ports and one USB port. It runs the same Nila Smart TV platform as the 55 inch model. Speaker output is 2 x 8 W.

## Nila PowerBlend 1200W Blender
The PowerBlend has a 1200 W motor, a 1.5 litre jar, a grinder jar for spices and three speed settings with a pulse function. The stainless steel blades can crush ice.

## Nila RiceMaster 1.8L Rice Cooker
The RiceMaster cooks up to 1.8 litres (about 10 cups) of rice. It has a non-stick inner pot, a steaming tray and an automatic keep-warm function that works for up to 12 hours.

## Nila BreezeLine 16 inch Pedestal Fan
The BreezeLine is a 16 inch pedestal fan with three speeds, side-to-side oscillation and adjustable height from 1.1 to 1.3 metres. It uses 55 W of power.
"""

CARE = """# Installation and Care Guide

## Before installation
Measure the space before you buy. Refrigerators need 10 cm of free space behind and on each side for air flow. Washing machines need a level floor; uneven floors cause shaking during the spin cycle.

## Air conditioner care
Clean the indoor dust filter every two weeks by rinsing it with water and letting it dry in the shade. Set the temperature to 25 or 26 degrees for the best balance of comfort and electricity cost. Close doors and windows while the air conditioner is running.

## Refrigerator care
After delivery, wait 4 hours before switching on a refrigerator so the oil in the compressor settles. Do not put hot food directly into the refrigerator. Clean the door seals with mild soapy water once a month.

## Washing machine care
Leave the door of a front load washer open after each wash so the drum can dry. Run an empty hot wash with a drum cleaner once a month. Clean the drain pump filter every three months.

## Power protection
Sri Lanka's power supply can have voltage changes and surges, especially during thunderstorms. Use a surge protector or voltage guard for air conditioners, refrigerators and televisions. Damage from power surges without a surge protector is not covered by the warranty.

## Energy saving
Inverter appliances use less electricity because their compressors and motors slow down instead of switching fully on and off. Choosing a correctly sized air conditioner for the room also saves electricity.
"""

CAREERS = """# Careers and Community

## Working at Nilaveli Electronics
Nilaveli Electronics employs about 140 people across its branches, service centres and head office in Colombo. We regularly hire sales executives, service technicians and customer care agents. Send your CV to careers@nilaveli-electronics.example with the job title in the subject line.

## Technician training programme
Every year the company trains 20 young technicians in a six month programme run by the Head of After-Sales Service. Trainees receive a monthly allowance and most are offered permanent jobs at the end of the programme.

## Community projects
Since 2018 the company has donated refrigerators to rural hospitals for storing vaccines, and runs an e-waste collection drive every June where customers can drop off old electronics of any brand at any branch for safe recycling.
"""


def write_docx(path: Path):
    d = docx.Document()
    d.styles["Normal"].font.size = Pt(10)
    d.add_heading("Nilaveli Electronics - Product Catalog 2026", 0)
    d.add_paragraph(
        "All prices are in Sri Lankan Rupees and include VAT. Prices are valid until 31 March 2027. "
        "The warranty plan for each product is explained in the Service and Warranty Policy."
    )
    for category, items in CATALOG:
        d.add_heading(category, 1)
        table = d.add_table(rows=1, cols=5)
        for cell, text in zip(table.rows[0].cells, ["Product", "Model", "Price", "Warranty plan", "Available at"]):
            cell.text = text
        for item in items:
            row = table.add_row().cells
            for cell, text in zip(row, item):
                cell.text = text
    d.add_heading("Notes", 1)
    d.add_paragraph("Products listed as available at selected branches can be ordered at any branch for home delivery.")
    d.save(path)


def write_pdf(path: Path):
    styles = getSampleStyleSheet()
    story = [Paragraph("Nilaveli Electronics - Service and Warranty Policy", styles["Title"]), Spacer(1, 12)]
    for i, (heading, paras) in enumerate(POLICIES):
        if i == 3:
            story.append(PageBreak())
        story.append(Paragraph(heading, styles["Heading2"]))
        for p in paras:
            story.append(Paragraph(p, styles["BodyText"]))
            story.append(Spacer(1, 6))
    SimpleDocTemplate(str(path), pagesize=A4, title="Service and Warranty Policy").build(story)


if __name__ == "__main__":
    (OUT / "01_company_profile.md").write_text(PROFILE, encoding="utf-8")
    write_docx(OUT / "02_product_catalog.docx")
    write_pdf(OUT / "03_service_and_warranty_policy.pdf")
    (OUT / "04_faq.txt").write_text(FAQ, encoding="utf-8")
    (OUT / "05_year_end_sale.html").write_text(PROMO_HTML, encoding="utf-8")
    (OUT / "06_product_specifications.md").write_text(SPECS, encoding="utf-8")
    (OUT / "07_installation_and_care_guide.md").write_text(CARE, encoding="utf-8")
    (OUT / "08_careers_and_community.md").write_text(CAREERS, encoding="utf-8")
    print("Wrote sample documents to", OUT)
