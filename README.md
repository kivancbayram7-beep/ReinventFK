# ReinventFK
A multi-tab desktop app for PDF &amp; image processing — convert, compress, decrypt, extract fonts, and handle comic book formats (CBR/CBZ).

# ReinventFK

A multi-tab PyQt5 desktop application for PDF and image processing, built for Windows.

## Features

### 📄 PDF Processing
- Convert PDF pages to TIFF, PNG, JPEG and other formats via pdftocairo
- Batch process multiple PDF files
- Cover page extraction (first/last N pages)
- Grayscale and monochrome output modes
- Custom DPI and scale options

### 🖼️ Image Processing
- Convert image folders to PDF with multiple compression modes:
  - JPEG (grayscale)
  - 1-bit black & white (ABBYY-style, smallest file size)
  - **img2pdf + CCITT Group 4** (recommended — lossless, near-ABBYY quality)
  - Multipage TIFF (LZW)
- Supported input formats: TIFF, JPEG, PNG, BMP, WebP

### 🔓 PDF Decryption
- Remove password protection from PDF files
- Tries without password first, then with user-supplied password
- Batch support

### 🔤 PDF Font Extraction
- List all embedded fonts in a PDF (name, type, format, subset status)
- Extract and save fonts (TTF, OTF, CFF)
- CID/CFF fonts: automatic conversion to TTF via fonttools
- Resizable columns, right-click for full font details

### 📦 Comic Book (CBR/CBZ)
- **PDF → CBR/CBZ**: Direct JPEG extraction from PDF (no re-encoding, fast)
- **CBR/CBZ → PDF**: Lossless packaging via img2pdf
- **CBR/CBZ Optimization**: Recompress with quality control (jpegoptim or Pillow)

### ⚙️ Settings
- JPEG quality and DPI defaults
- WinRAR and jpegoptim paths
- EXIF stripping toggle
- Tab ordering and visibility (drag & drop or arrows)
- Saved to `settings.json` alongside the executable

## Requirements

### Runtime (bundled in the release .exe)
- Python 3.x
- PyQt5
- Pillow
- pikepdf
- img2pdf
- PyMuPDF (fitz)
- fonttools
- py7zr

### External tools (place in subfolders next to the .exe)
| Tool | Folder | Purpose |
|------|--------|---------|
| pdftocairo.exe | `./pdftocairo/` | PDF → image conversion |
| pdfinfo.exe | `./pdftocairo/` | Page count detection |
| unrar.exe | `./unrar/` | CBR extraction (optional) |
| WinRAR.exe | system or configured path | CBR creation (optional) |
| jpegoptim.exe | configured path | JPEG optimization (optional) |
| icon.ico | next to .exe | Application icon (optional) |

> pdftocairo and pdfinfo are part of the [Poppler](https://poppler.freedesktop.org/) distribution for Windows.

## Building from Source

```powershell
pip install PyQt5 Pillow pikepdf img2pdf pymupdf fonttools py7zr pyinstaller

pyinstaller --noconsole --onefile `
  --collect-all=pikepdf `
  --collect-all=fitz `
  --collect-all=fontTools `
  --hidden-import=img2pdf `
  --hidden-import=py7zr `
  ReinventFK_v4.7.py
```

## Notes

- Turkish character support: files with non-ASCII paths are handled via temporary ASCII copies
- CBR output without WinRAR uses ZIP-based packaging (compatible with all major comic readers)
- Tab layout and visibility preferences persist across sessions via `settings.json`

## License

MIT License — see [LICENSE](LICENSE) for details.
