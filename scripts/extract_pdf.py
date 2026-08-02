import fitz
import sys

doc = fitz.open(r'C:\Users\owner\Downloads\20260801_コード理解サポートエージェント_検討整理 - シート1.pdf')
text = "\n".join([page.get_text() for page in doc])

output_path = r'C:\Users\owner\Documents\lab\Antigravity\DeDoubt\scripts\pdf_output.txt'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(text)

print(f"Output written to {output_path}")
print(f"Total pages: {len(doc)}")
print(f"Total characters: {len(text)}")
