from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def create_sample_pdf(filename):
    c = canvas.Canvas(filename, pagesize=letter)
    c.drawString(100, 750, "Hello World from Stirling SDG!")
    c.drawString(100, 730, "This is a sample PDF for testing direct editing.")
    c.drawString(100, 710, "Target Text: TO_REPLACE")
    c.drawString(100, 690, "Footer text.")
    c.save()

if __name__ == "__main__":
    create_sample_pdf("sample.pdf")
    print("Created sample.pdf")
