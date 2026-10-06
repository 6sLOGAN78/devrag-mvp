# Office Documents Subsystem

## Level 1: Conceptual Overview

The Office Documents subsystem parses DOCX (Microsoft Word), XLSX (Microsoft Excel), and PPTX (Microsoft PowerPoint) files into structured text blocks, tables, and embedded images while preserving document structure.

---

## Level 2: Implementation Details

### Parser Implementations

1. **DOCX Parsing (`docx_parser.py`)**:
   - Python: [deepdoc/parser/docx_parser.py](file:///home/logan78/Desktop/ragflow/deepdoc/parser/docx_parser.py#L25)
   - Go: [internal/deepdoc/parser/docx/parser.go](file:///home/logan78/Desktop/ragflow/internal/deepdoc/parser/docx/parser.go#L30)
   - Reads document XML trees (`w:p`, `w:tbl`, `w:r`, `w:drawing`).
   - Converts Word tables directly to HTML string structures `<table border='1'>...</table>`.

2. **Excel Parsing (`excel_parser.py`)**:
   - Source: [deepdoc/parser/excel_parser.py](file:///home/logan78/Desktop/ragflow/deepdoc/parser/excel_parser.py#L20)
   - Iterates across openpyxl worksheets.
   - Formats table rows into Markdown / HTML representations with header row context attached.

3. **PowerPoint Parsing (`ppt_parser.py`)**:
   - Source: [deepdoc/parser/ppt_parser.py](file:///home/logan78/Desktop/ragflow/deepdoc/parser/ppt_parser.py#L20)
   - Extracts slide titles, text frames, shape tables, and slide speaker notes.
