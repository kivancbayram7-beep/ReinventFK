import sys
import os
import re
import glob
import platform
import subprocess
import shutil
import tempfile
import time

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox, QCheckBox,
    QMessageBox, QSpinBox, QHBoxLayout, QTabWidget, QDoubleSpinBox
)
from PyQt5.QtCore import Qt
from PIL import Image


# ──────────────────────────────────────────────
#  Yardımcı fonksiyonlar
# ──────────────────────────────────────────────

def natural_sort(lst):
    convert = lambda t: int(t) if t.isdigit() else t.lower()
    return sorted(set(lst), key=lambda k: [convert(c) for c in re.split(r'([0-9]+)', k)])

def has_non_ascii(path):
    try:
        path.encode('ascii')
        return False
    except UnicodeEncodeError:
        return True

def make_startupinfo():
    if platform.system() == 'Windows':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        return si
    return None


# ──────────────────────────────────────────────
#  SEKME 1 — PDF İşleme  (v1.8.1 kodu aynen)
# ──────────────────────────────────────────────

class PDFTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        grid   = QGridLayout()
        row    = 0

        # PDF seçimi (çoklu)
        grid.addWidget(QLabel("PDF Seç:"), row, 0)
        self.pdf_entry = QLineEdit()
        self.pdf_entry.setPlaceholderText("Bir veya birden fazla PDF seçilebilir...")
        grid.addWidget(self.pdf_entry, row, 1)
        grid.addWidget(QPushButton("Gözat", clicked=self.browse_pdf), row, 2)
        row += 1

        # Sayfa Aralığı — tek satırda
        grid.addWidget(QLabel("Sayfa Aralığı:"), row, 0)
        pr_widget = QWidget()
        pr_layout = QHBoxLayout(pr_widget)
        pr_layout.setContentsMargins(0, 0, 0, 0)
        self.first_page_spin = QSpinBox(); self.first_page_spin.setRange(1, 99999); self.first_page_spin.setValue(1)
        self.last_page_spin  = QSpinBox(); self.last_page_spin.setRange(1, 99999);  self.last_page_spin.setValue(99999)
        pr_layout.addWidget(self.first_page_spin)
        pr_layout.addWidget(QLabel("-"))
        pr_layout.addWidget(self.last_page_spin)
        pr_layout.addStretch()
        grid.addWidget(pr_widget, row, 1)
        row += 1

        # Çıktı formatı
        grid.addWidget(QLabel("Çıktı Uzantısı:"), row, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["png", "jpeg", "tiff", "pdf", "ps", "eps", "svg"])
        self.format_combo.setCurrentText("tiff")
        self.format_combo.currentTextChanged.connect(self._toggle_tiff)
        grid.addWidget(self.format_combo, row, 1)
        row += 1

        # Çözünürlük
        grid.addWidget(QLabel("Çözünürlük (DPI):"), row, 0)
        self.resolution_spin = QSpinBox(); self.resolution_spin.setRange(1, 10000); self.resolution_spin.setValue(300)
        grid.addWidget(self.resolution_spin, row, 1)
        row += 1

        # Ölçek — tek satırda
        grid.addWidget(QLabel("Manuel Ölçek (px):"), row, 0)
        sc_widget = QWidget(); sc_layout = QHBoxLayout(sc_widget); sc_layout.setContentsMargins(0,0,0,0)
        self.manual_scale_spin = QSpinBox(); self.manual_scale_spin.setRange(0, 20000); self.manual_scale_spin.setValue(0)
        self.manual_scale_spin.setFixedWidth(70); self.manual_scale_spin.setEnabled(False)
        self.scale_3000_check  = QCheckBox("3000px Sabit"); self.scale_3000_check.setChecked(True)
        self.scale_3000_check.toggled.connect(lambda c: self.manual_scale_spin.setEnabled(not c))
        sc_layout.addWidget(self.manual_scale_spin); sc_layout.addWidget(self.scale_3000_check); sc_layout.addStretch()
        grid.addWidget(sc_widget, row, 1)
        row += 1

        # Renk seçenekleri
        self.grayscale_check  = QCheckBox("Grayscale (Gri Tonlamalı)")
        self.grayscale_check.setChecked(True)
        self.grayscale_check.setStyleSheet("font-weight:bold; color:gray;")
        grid.addWidget(self.grayscale_check, row, 1); row += 1

        self.monochrome_check = QCheckBox("Siyah-Beyaz (Monochrome)")
        self.monochrome_check.setStyleSheet("font-weight:bold; color:black;")
        grid.addWidget(self.monochrome_check, row, 1); row += 1

        self.grayscale_check.toggled.connect(lambda c: self.monochrome_check.setChecked(False) if c else None)
        self.monochrome_check.toggled.connect(lambda c: self.grayscale_check.setChecked(False)  if c else None)

        # TIFF Birleştir
        self.combine_tiff_check = QCheckBox("TIFF Sayfalarını Birleştir (Multipage)")
        self.combine_tiff_check.setChecked(False)
        self.combine_tiff_check.setStyleSheet("font-weight:bold; color:green;")
        grid.addWidget(self.combine_tiff_check, row, 1); row += 1

        # Kapak sayfaları
        cv_widget = QWidget(); cv_layout = QHBoxLayout(cv_widget); cv_layout.setContentsMargins(0,0,0,0)
        self.cover_pages_check = QCheckBox("Kapak Sayfalarını Çıkar (Renkli)  ±")
        self.cover_pages_check.setStyleSheet("font-weight:bold; color:darkred;")
        self.cover_pages_spin  = QSpinBox(); self.cover_pages_spin.setRange(1,99); self.cover_pages_spin.setValue(3)
        self.cover_pages_spin.setFixedWidth(50); self.cover_pages_spin.setToolTip("İlk ve son kaç sayfa?")
        self.cover_pages_check.toggled.connect(self._on_cover_toggled)
        cv_layout.addWidget(self.cover_pages_check); cv_layout.addWidget(self.cover_pages_spin); cv_layout.addStretch()
        grid.addWidget(cv_widget, row, 1); row += 1

        layout.addLayout(grid)

        # Dönüştür butonu
        btn = QPushButton("DÖNÜŞTÜR (PDF İşleme)", clicked=self.convert)
        btn.setFixedHeight(40)
        btn.setStyleSheet("background-color:#4CAF50; color:white; font-weight:bold;")
        layout.addWidget(btn)

        self.status_label = QLabel("Hazır.", styleSheet="color:blue;")
        layout.addWidget(self.status_label)
        layout.addStretch()

    # ── sinyaller ──
    def _toggle_tiff(self, text):
        self.combine_tiff_check.setEnabled(text == "tiff")

    def _on_cover_toggled(self, checked):
        if checked:
            self.grayscale_check.setChecked(False)
            self.monochrome_check.setChecked(False)
        self.grayscale_check.setEnabled(not checked)
        self.monochrome_check.setEnabled(not checked)

    def browse_pdf(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "PDF Seç", "", "PDF files (*.pdf)")
        if paths:
            self.pdf_entry.setText("; ".join(paths))

    def get_pdf_page_count(self, pdf_file, si=None):
        # Yöntem 1: pdfinfo.exe (poppler)
        pdfinfo = os.path.abspath("./pdftocairo/pdfinfo.exe")
        if os.path.exists(pdfinfo):
            try:
                r = subprocess.run([pdfinfo, pdf_file], capture_output=True, text=True, startupinfo=si)
                for line in r.stdout.splitlines():
                    if line.lower().startswith("pages:"):
                        return int(line.split(":")[1].strip())
            except Exception:
                pass

        # Yöntem 2: pikepdf
        try:
            import pikepdf
            with pikepdf.open(pdf_file) as pdf:
                return len(pdf.pages)
        except Exception:
            pass

        # Yöntem 3: pymupdf (fitz)
        try:
            import fitz
            doc = fitz.open(pdf_file)
            count = len(doc)
            doc.close()
            return count
        except Exception:
            pass

        # Yöntem 4: Pillow (genellikle PDF için çalışmaz ama son çare)
        try:
            img = Image.open(pdf_file)
            return img.n_frames
        except Exception:
            pass

        return None

    # ── Ana dönüştürme ──
    def convert(self):
        raw = self.pdf_entry.text().strip()
        if not raw:
            QMessageBox.warning(self, "Hata", "Lütfen en az bir PDF seçin!"); return

        pdf_list = [os.path.normpath(p.strip()) for p in raw.split(";") if p.strip()]
        missing  = [p for p in pdf_list if not os.path.exists(p)]
        if missing:
            QMessageBox.warning(self, "Hata", "Bulunamadı:\n" + "\n".join(missing)); return

        out_fmt     = self.format_combo.currentText()
        res         = self.resolution_spin.value()
        scale_val   = 3000 if self.scale_3000_check.isChecked() else self.manual_scale_spin.value()
        is_multi    = self.combine_tiff_check.isChecked() and out_fmt == "tiff"
        cover_mode  = self.cover_pages_check.isChecked()
        exe_path    = os.path.abspath("./pdftocairo/pdftocairo.exe")
        si          = make_startupinfo()
        results     = []
        errors      = []

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for pdf_file in pdf_list:
                pdf_dir  = os.path.dirname(pdf_file)
                pdf_name = os.path.splitext(os.path.basename(pdf_file))[0]
                # Kapak modunda _kapaklar, normal modda _images klasörü
                folder_suffix = "_kapaklar" if cover_mode else "_images"
                out_dir  = os.path.join(pdf_dir, f"{pdf_name}{folder_suffix}")
                os.makedirs(out_dir, exist_ok=True)

                temp_dir   = None
                temp_out   = None   # Türkçe karakterli çıktı klasörü için
                work_file  = pdf_file
                actual_out = out_dir   # gerçek hedef klasör

                if has_non_ascii(pdf_file):
                    try:
                        temp_dir  = tempfile.mkdtemp()
                        work_file = os.path.join(temp_dir, "input_temp.pdf")
                        shutil.copy2(pdf_file, work_file)
                    except Exception:
                        errors.append(f"✘ {pdf_name}: Geçici dosya oluşturulamadı — atlandı.")
                        continue

                # Çıktı klasörü yolu da Türkçe/özel karakter içeriyorsa temp klasör kullan
                if has_non_ascii(out_dir):
                    temp_out   = tempfile.mkdtemp()
                    actual_out = temp_out

                try:
                    if cover_mode:
                        self.status_label.setText(f"Sayfa sayısı: {pdf_name}"); QApplication.processEvents()
                        pc = self.get_pdf_page_count(work_file, si)
                        if pc is None:
                            errors.append(f"✘ {pdf_name}: Sayfa sayısı okunamadı — atlandı.")
                            continue
                        n  = self.cover_pages_spin.value()
                        pages = sorted(set(range(1, min(n+1, pc+1))) | set(range(max(pc-n+1,1), pc+1)))
                        self.status_label.setText(f"Kapak çıkarılıyor: {pdf_name}"); QApplication.processEvents()
                        for pg in pages:
                            pfx = os.path.join(actual_out, f"kapak_sayfa_{pg:04d}")
                            cmd = [exe_path, f"-{out_fmt}", "-r", str(res), "-f", str(pg), "-l", str(pg), "-singlefile"]
                            if scale_val > 0: cmd.extend(["-scale-to", str(scale_val)])
                            cmd.extend([work_file, pfx])
                            subprocess.run(cmd, check=True, startupinfo=si)
                        time.sleep(0.5)
                        gen = []
                        for pg in pages:
                            pfx = os.path.join(actual_out, f"kapak_sayfa_{pg:04d}")
                            for candidate in glob.glob(f"{pfx}.*"):
                                if candidate not in gen:
                                    gen.append(candidate)
                        gen = natural_sort(gen)
                        if out_fmt == "tiff":
                            for f in gen:
                                with Image.open(f) as img: img.save(f, compression="tiff_lzw", dpi=(float(res),)*2)
                        # Eğer temp_out kullanıldıysa dosyaları gerçek klasöre taşı
                        if temp_out:
                            moved = []
                            for f in gen:
                                dst = os.path.join(out_dir, os.path.basename(f))
                                shutil.move(f, dst)
                                moved.append(dst)
                            gen = moved
                        results.append(f"✔ {pdf_name}: {len(gen)} kapak dosyası (sayfalar: {pages})")

                    else:
                        self.status_label.setText(f"Dönüştürülüyor: {pdf_name}"); QApplication.processEvents()
                        pfx = os.path.join(actual_out, "temp_page")
                        cmd = [exe_path, f"-{out_fmt}", "-r", str(res),
                               "-f", str(self.first_page_spin.value()), "-l", str(self.last_page_spin.value())]
                        if scale_val > 0: cmd.extend(["-scale-to", str(scale_val)])
                        if self.monochrome_check.isChecked(): cmd.append("-mono")
                        elif self.grayscale_check.isChecked(): cmd.append("-gray")
                        cmd.extend([work_file, pfx])
                        subprocess.run(cmd, check=True, startupinfo=si)
                        time.sleep(1)
                        files = []
                        for ext in ["*.tiff", "*.tif"]: files.extend(glob.glob(os.path.join(actual_out, ext)))
                        files = natural_sort(files)
                        # Eğer temp_out kullanıldıysa dosyaları gerçek klasöre taşı
                        if temp_out:
                            moved = []
                            for f in files:
                                dst = os.path.join(out_dir, os.path.basename(f))
                                shutil.move(f, dst)
                                moved.append(dst)
                            files = moved
                        if is_multi and files:
                            self.status_label.setText(f"Birleştiriliyor: {pdf_name}"); QApplication.processEvents()
                            imgs = [Image.open(f) for f in files]
                            fp   = os.path.join(out_dir, f"{pdf_name}_Multipage_LZW.tiff")
                            imgs[0].save(fp, save_all=True, append_images=imgs[1:],
                                         compression="tiff_lzw", dpi=(float(res),)*2)
                            for i in imgs: i.close()
                            for f in files: os.remove(f)
                            results.append(f"✔ {pdf_name}: Multipage TIFF hazır.")
                        else:
                            for f in files:
                                with Image.open(f) as img: img.save(f, compression="tiff_lzw", dpi=(float(res),)*2)
                            results.append(f"✔ {pdf_name}: {len(files)} TIFF dosyası hazır.")
                finally:
                    if temp_dir: shutil.rmtree(temp_dir, ignore_errors=True)
                    if temp_out: shutil.rmtree(temp_out, ignore_errors=True)

            QApplication.restoreOverrideCursor()
            msg_parts = []
            if results:
                msg_parts.append("\n".join(results))
            if errors:
                msg_parts.append("─── Atlanan Dosyalar ───\n" + "\n".join(errors))
            final_msg = "\n\n".join(msg_parts) if msg_parts else "İşlem tamamlandı."

            # Kaydırmalı rapor dialogu
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel
            dlg = QDialog(self)
            dlg.setWindowTitle("İşlem Raporu" + (" — Bazı Hatalar" if errors else ""))
            dlg.setMinimumSize(500, 350)
            dlg_layout = QVBoxLayout(dlg)
            lbl = QLabel("✔ Başarılı" if not errors else
                         ("✘ Tüm dosyalar atlandı" if not results else f"✔ {len(results)} başarılı  ✘ {len(errors)} atlandı"))
            lbl.setStyleSheet("font-weight:bold; font-size:11px; color:" + ("green" if not errors else ("red" if not results else "darkorange")))
            dlg_layout.addWidget(lbl)
            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setPlainText(final_msg)
            txt.setFont(txt.font())
            dlg_layout.addWidget(txt)
            close_btn = QPushButton("Kapat")
            close_btn.clicked.connect(dlg.accept)
            dlg_layout.addWidget(close_btn)
            dlg.exec_()

            self.status_label.setText("Hazır.")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Hata", str(e))
            self.status_label.setText("Hata oluştu.")


# ──────────────────────────────────────────────
#  SEKME 2 — Resim İşleme
# ──────────────────────────────────────────────

class ImageTab(QWidget):
    SUPPORTED_EXTS = ["*.tiff", "*.tif", "*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"]

    # Format indeksleri
    FMT_PDF_JPEG   = 0   # PDF (Gri - JPEG sıkıştırma)
    FMT_PDF_1BIT   = 1   # PDF (Siyah-Beyaz - 1bit)
    FMT_TIFF_MULTI = 2   # TIFF Multipage LZW
    FMT_PDF_G4     = 3   # PDF (img2pdf + CCITT Group 4)

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        grid   = QGridLayout()
        row    = 0

        # Klasör seçimi
        grid.addWidget(QLabel("Klasör Seç:"), row, 0)
        self.folder_entry = QLineEdit()
        self.folder_entry.setPlaceholderText("İçinde resim dosyaları bulunan klasör...")
        grid.addWidget(self.folder_entry, row, 1)
        grid.addWidget(QPushButton("Gözat", clicked=self.browse_folder), row, 2)
        row += 1

        # Çıktı formatı — 4 seçenek
        grid.addWidget(QLabel("Çıktı Formatı:"), row, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "PDF (Gri - JPEG sıkıştırma)",
            "PDF (Siyah-Beyaz - 1bit)",
            "TIFF (Multipage LZW)",
            "PDF (img2pdf + CCITT Group 4)  ★",
        ])
        self.format_combo.setCurrentIndex(self.FMT_PDF_G4)   # varsayılan
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        grid.addWidget(self.format_combo, row, 1)
        row += 1

        # PDF kalite satırı — sadece JPEG modunda görünür
        self.quality_label = QLabel("PDF Kalitesi:")
        grid.addWidget(self.quality_label, row, 0)
        qual_widget = QWidget()
        qual_layout = QHBoxLayout(qual_widget); qual_layout.setContentsMargins(0,0,0,0)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(70)
        self.quality_spin.setSuffix("%")
        self.quality_spin.setFixedWidth(75)
        self.quality_spin.setToolTip(
            "JPEG kalitesi (1-100).\n"
            "70 → iyi denge (dosya küçük, kalite yeterli)\n"
            "85 → yüksek kalite\n"
            "95+ → neredeyse kayıpsız ama büyük dosya"
        )
        self.quality_info = QLabel("(JPEG sıkıştırma — gri tonlamalı sayfalar için)")
        qual_layout.addWidget(self.quality_spin)
        qual_layout.addWidget(self.quality_info)
        qual_layout.addStretch()
        grid.addWidget(qual_widget, row, 1)
        self.quality_row_widget = qual_widget   # gizlemek için referans
        row += 1

        # 1-bit uyarı satırı — sadece 1-bit modunda görünür
        self.onebit_label = QLabel("⚠ Uyarı:")
        grid.addWidget(self.onebit_label, row, 0)
        self.onebit_info = QLabel(
            "Her piksel tam siyah veya tam beyaz olur.\n"
            "Metin sayfaları için idealdir; fotoğraf/görsel içeren\n"
            "sayfalarda görsel kalitesi bozulur."
        )
        self.onebit_info.setStyleSheet("color: darkred; font-size: 10px;")
        grid.addWidget(self.onebit_info, row, 1)
        self.onebit_row_label  = self.onebit_label
        self.onebit_row_widget = self.onebit_info
        row += 1

        # G4 bilgi satırı — sadece G4 modunda görünür
        self.g4_label = QLabel("ℹ Bilgi:")
        grid.addWidget(self.g4_label, row, 0)
        self.g4_info = QLabel(
            "img2pdf + CCITT Group 4 (faks sıkıştırması).\n"
            "En küçük dosya boyutu. Sadece siyah-beyaz/gri TIFF\n"
            "dosyaları için önerilir. Renkli dosyalar otomatik\n"
            "dönüştürülür ancak renk bilgisi kaybolur."
        )
        self.g4_info.setStyleSheet("color: darkblue; font-size: 10px;")
        grid.addWidget(self.g4_info, row, 1)
        self.g4_row_label  = self.g4_label
        self.g4_row_widget = self.g4_info
        row += 1

        # Çıktı dosya adı
        grid.addWidget(QLabel("Çıktı Adı:"), row, 0)
        self.output_name_entry = QLineEdit()
        self.output_name_entry.setPlaceholderText("Boş bırakılırsa klasör adı kullanılır...")
        grid.addWidget(self.output_name_entry, row, 1)
        row += 1

        layout.addLayout(grid)

        # Buton
        btn = QPushButton("İŞLE (Resim → Çıktı)", clicked=self.process)
        btn.setFixedHeight(40)
        btn.setStyleSheet("background-color:#1976D2; color:white; font-weight:bold;")
        layout.addWidget(btn)

        self.status_label = QLabel("Hazır.", styleSheet="color:blue;")
        layout.addWidget(self.status_label)
        layout.addStretch()

        # Başlangıç görünümü ayarla
        self._on_format_changed(self.FMT_PDF_G4)

    def _on_format_changed(self, idx):
        is_jpeg = (idx == self.FMT_PDF_JPEG)
        is_1bit = (idx == self.FMT_PDF_1BIT)
        is_g4   = (idx == self.FMT_PDF_G4)

        self.quality_label.setVisible(is_jpeg)
        self.quality_row_widget.setVisible(is_jpeg)
        self.onebit_row_label.setVisible(is_1bit)
        self.onebit_row_widget.setVisible(is_1bit)
        self.g4_row_label.setVisible(is_g4)
        self.g4_row_widget.setVisible(is_g4)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Klasör Seç", "")
        if folder:
            self.folder_entry.setText(folder)

    def _collect_images(self, folder):
        files = []
        for ext in self.SUPPORTED_EXTS:
            files.extend(glob.glob(os.path.join(folder, ext)))
            files.extend(glob.glob(os.path.join(folder, ext.upper())))
        return natural_sort(files)

    def _read_dpi(self, img):
        """Pillow Image nesnesinden DPI okur, bulamazsa (96,96) döner."""
        info = img.info or {}
        if "dpi" in info:
            try:
                return (float(info["dpi"][0]), float(info["dpi"][1]))
            except Exception:
                pass
        if "resolution" in info:
            try:
                r = float(info["resolution"])
                return (r, r)
            except Exception:
                pass
        return (96.0, 96.0)

    def process(self):
        folder = self.folder_entry.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir klasör seçin!"); return

        files = self._collect_images(folder)
        if not files:
            QMessageBox.warning(self, "Hata",
                "Klasörde desteklenen resim dosyası bulunamadı!\n"
                f"Aranan uzantılar: {', '.join(self.SUPPORTED_EXTS)}"); return

        fmt_idx  = self.format_combo.currentIndex()
        quality  = self.quality_spin.value()
        out_name = self.output_name_entry.text().strip() or os.path.basename(folder)
        out_dir  = folder

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # ── FORMAT 0: PDF (Gri - JPEG) ──────────────────────────────
            if fmt_idx == self.FMT_PDF_JPEG:
                images_out, dpis = [], []
                for i, fpath in enumerate(files):
                    self.status_label.setText(f"Yükleniyor: {i+1}/{len(files)}  {os.path.basename(fpath)}")
                    QApplication.processEvents()
                    img = Image.open(fpath)
                    dpi = self._read_dpi(img)
                    # Mod: L ve RGB olduğu gibi; diğerleri dönüştür
                    if img.mode in ("RGBA", "LA"):
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        bg.paste(img, mask=img.split()[-1]); img = bg
                    elif img.mode == "P":
                        img = img.convert("RGB")
                    elif img.mode == "1":
                        img = img.convert("L")
                    elif img.mode not in ("L", "RGB"):
                        img = img.convert("RGB")
                    images_out.append(img); dpis.append(dpi)

                out_path = os.path.join(out_dir, f"{out_name}.pdf")
                self.status_label.setText("PDF oluşturuluyor..."); QApplication.processEvents()

                from collections import Counter
                dominant_dpi = Counter(dpis).most_common(1)[0][0]
                images_out[0].save(
                    out_path, format="PDF", save_all=True,
                    append_images=images_out[1:],
                    quality=quality, resolution=dominant_dpi[0],
                )
                for img in images_out: img.close()
                size_mb = os.path.getsize(out_path) / (1024*1024)
                msg = (f"PDF (Gri/JPEG) oluşturuldu!\n"
                       f"Dosya: {out_path}\n"
                       f"Sayfa: {len(files)}  |  Boyut: {size_mb:.1f} MB\n"
                       f"Kalite: %{quality}  |  DPI: {int(dominant_dpi[0])}")

            # ── FORMAT 1: PDF (Siyah-Beyaz - 1bit) ──────────────────────
            elif fmt_idx == self.FMT_PDF_1BIT:
                images_out, dpis = [], []
                for i, fpath in enumerate(files):
                    self.status_label.setText(f"1-bit dönüşüm: {i+1}/{len(files)}  {os.path.basename(fpath)}")
                    QApplication.processEvents()
                    img = Image.open(fpath)
                    dpi = self._read_dpi(img)
                    # Her modu önce L'ye (grayscale), sonra 1-bit'e çevir
                    # dither=0 → eşikleme (threshold), FLOYDSTEINBERG daha yumuşak ama yavaş
                    if img.mode != "L":
                        img = img.convert("L")
                    img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
                    images_out.append(img); dpis.append(dpi)

                out_path = os.path.join(out_dir, f"{out_name}_1bit.pdf")
                self.status_label.setText("1-bit PDF oluşturuluyor..."); QApplication.processEvents()

                from collections import Counter
                dominant_dpi = Counter(dpis).most_common(1)[0][0]
                images_out[0].save(
                    out_path, format="PDF", save_all=True,
                    append_images=images_out[1:],
                    resolution=dominant_dpi[0],
                )
                for img in images_out: img.close()
                size_mb = os.path.getsize(out_path) / (1024*1024)
                msg = (f"PDF (Siyah-Beyaz 1-bit) oluşturuldu!\n"
                       f"Dosya: {out_path}\n"
                       f"Sayfa: {len(files)}  |  Boyut: {size_mb:.1f} MB\n"
                       f"DPI: {int(dominant_dpi[0])}")

            # ── FORMAT 2: TIFF Multipage LZW ────────────────────────────
            elif fmt_idx == self.FMT_TIFF_MULTI:
                images_out = []
                for i, fpath in enumerate(files):
                    self.status_label.setText(f"Yükleniyor: {i+1}/{len(files)}  {os.path.basename(fpath)}")
                    QApplication.processEvents()
                    images_out.append(Image.open(fpath))

                out_path = os.path.join(out_dir, f"{out_name}_Multipage_LZW.tiff")
                self.status_label.setText("Multipage TIFF oluşturuluyor..."); QApplication.processEvents()
                images_out[0].save(
                    out_path, save_all=True,
                    append_images=images_out[1:],
                    compression="tiff_lzw",
                )
                for img in images_out: img.close()
                size_mb = os.path.getsize(out_path) / (1024*1024)
                msg = (f"Multipage TIFF (LZW) oluşturuldu!\n"
                       f"Dosya: {out_path}\n"
                       f"Sayfa: {len(files)}  |  Boyut: {size_mb:.1f} MB")

            # ── FORMAT 3: PDF (img2pdf + CCITT Group 4) ─────────────────
            elif fmt_idx == self.FMT_PDF_G4:
                try:
                    import img2pdf
                except ImportError as e:
                    QApplication.restoreOverrideCursor()
                    QMessageBox.critical(self, "Eksik Paket",
                        f"Gerekli paket bulunamadı: {e}\n\n"
                        "Lütfen şunu çalıştırın:\n  pip install img2pdf")
                    return

                out_path = os.path.join(out_dir, f"{out_name}_G4.pdf")
                tmp_g4_dir = tempfile.mkdtemp()

                try:
                    g4_files = []
                    for i, fpath in enumerate(files):
                        self.status_label.setText(
                            f"G4 dönüşüm: {i+1}/{len(files)}  {os.path.basename(fpath)}")
                        QApplication.processEvents()

                        img = Image.open(fpath)

                        # 1. Modu normalize et: önce L (grayscale), sonra 1-bit
                        if img.mode not in ("L", "1"):
                            img = img.convert("L")
                        if img.mode == "L":
                            img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

                        # 2. Group 4 TIFF olarak kaydet
                        tmp_tiff = os.path.join(tmp_g4_dir, f"g4_{i:05d}.tiff")
                        img.save(tmp_tiff, format="TIFF", compression="group4")
                        img.close()
                        g4_files.append(tmp_tiff)

                    # 3. img2pdf ile tek PDF'e birleştir (piksel dokunmaz, G4 korunur)
                    self.status_label.setText("img2pdf: PDF oluşturuluyor...")
                    QApplication.processEvents()
                    with open(out_path, "wb") as f:
                        f.write(img2pdf.convert(g4_files))

                finally:
                    shutil.rmtree(tmp_g4_dir, ignore_errors=True)

                size_mb = os.path.getsize(out_path) / (1024*1024)
                msg = (f"PDF (CCITT Group 4) oluşturuldu!\n"
                       f"Dosya: {out_path}\n"
                       f"Sayfa: {len(files)}  |  Boyut: {size_mb:.1f} MB\n"
                       f"Sıkıştırma: CCITT Group 4 (faks)")


            QApplication.restoreOverrideCursor()
            QMessageBox.information(self, "İşlem Tamam", msg)
            self.status_label.setText("Hazır.")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Hata", str(e))
            self.status_label.setText("Hata oluştu.")


# ──────────────────────────────────────────────
#  SEKME 3 — Şifre Çöz
# ──────────────────────────────────────────────

class DecryptTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        grid   = QGridLayout()
        row    = 0

        # PDF seçimi (çoklu)
        grid.addWidget(QLabel("PDF Seç:"), row, 0)
        self.pdf_entry = QLineEdit()
        self.pdf_entry.setPlaceholderText("Bir veya birden fazla şifreli PDF seçilebilir...")
        grid.addWidget(self.pdf_entry, row, 1)
        grid.addWidget(QPushButton("Gözat", clicked=self.browse_pdf), row, 2)
        row += 1

        # Şifre girişi
        grid.addWidget(QLabel("Şifre:"), row, 0)
        pw_widget = QWidget()
        pw_layout = QHBoxLayout(pw_widget); pw_layout.setContentsMargins(0,0,0,0)
        self.password_entry = QLineEdit()
        self.password_entry.setPlaceholderText("Boş bırakılırsa şifresiz denenir...")
        self.password_entry.setEchoMode(QLineEdit.Password)
        self.show_pw_check = QCheckBox("Göster")
        self.show_pw_check.toggled.connect(
            lambda c: self.password_entry.setEchoMode(
                QLineEdit.Normal if c else QLineEdit.Password))
        pw_layout.addWidget(self.password_entry)
        pw_layout.addWidget(self.show_pw_check)
        grid.addWidget(pw_widget, row, 1)
        row += 1

        # Bilgi notu
        info = QLabel(
            "ℹ  Önce şifresiz açılmaya çalışılır.\n"
            "   Başarısız olursa girilen şifre ile denenir.\n"
            "   Çıktı: orijinal klasöre  dosyaadi_decrypted.pdf"
        )
        info.setStyleSheet("color: #555; font-size: 10px;")
        grid.addWidget(info, row, 1)
        row += 1

        layout.addLayout(grid)

        btn = QPushButton("ŞİFREYİ KALDIR", clicked=self.decrypt)
        btn.setFixedHeight(40)
        btn.setStyleSheet("background-color:#7B1FA2; color:white; font-weight:bold;")
        layout.addWidget(btn)

        self.status_label = QLabel("Hazır.", styleSheet="color:blue;")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def browse_pdf(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Şifreli PDF Seç", "", "PDF files (*.pdf)")
        if paths:
            self.pdf_entry.setText("; ".join(paths))

    def decrypt(self):
        raw = self.pdf_entry.text().strip()
        if not raw:
            QMessageBox.warning(self, "Hata", "Lütfen en az bir PDF seçin!"); return

        pdf_list = [os.path.normpath(p.strip()) for p in raw.split(";") if p.strip()]
        missing  = [p for p in pdf_list if not os.path.exists(p)]
        if missing:
            QMessageBox.warning(self, "Hata", "Bulunamadı:\n" + "\n".join(missing)); return

        password = self.password_entry.text()  # boş olabilir

        try:
            import pikepdf
        except ImportError:
            QMessageBox.critical(self, "Eksik Paket",
                "pikepdf bulunamadı.\npip install pikepdf"); return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        results  = []
        errors   = []

        try:
            for pdf_file in pdf_list:
                pdf_dir  = os.path.dirname(pdf_file)
                pdf_name = os.path.splitext(os.path.basename(pdf_file))[0]
                out_path = os.path.join(pdf_dir, f"{pdf_name}_decrypted.pdf")

                self.status_label.setText(f"İşleniyor: {pdf_name}")
                QApplication.processEvents()

                opened = False

                # 1. Şifresiz dene
                try:
                    pdf = pikepdf.open(pdf_file)
                    opened = True
                    method = "şifresiz"
                except pikepdf.PasswordError:
                    pass

                # 2. Girilen şifreyle dene
                if not opened and password:
                    try:
                        pdf = pikepdf.open(pdf_file, password=password)
                        opened = True
                        method = "girilen şifre ile"
                    except pikepdf.PasswordError:
                        pass

                if not opened:
                    if password:
                        errors.append(f"✘ {pdf_name}: Şifre hatalı veya desteklenmiyor.")
                    else:
                        errors.append(f"✘ {pdf_name}: Şifre korumalı — lütfen şifreyi girin.")
                    continue

                # Şifresi açık PDF'i kaydet
                pdf.save(out_path)
                pdf.close()

                size_mb = os.path.getsize(out_path) / (1024*1024)
                results.append(f"✔ {pdf_name}: Başarılı ({method}), {size_mb:.1f} MB")

            QApplication.restoreOverrideCursor()

            msg_parts = []
            if results: msg_parts.append("\n".join(results))
            if errors:  msg_parts.append("\n".join(errors))
            final_msg = "\n\n".join(msg_parts)

            if errors and not results:
                QMessageBox.critical(self, "Başarısız", final_msg)
            elif errors:
                QMessageBox.warning(self, "Kısmen Başarılı", final_msg)
            else:
                QMessageBox.information(self, "İşlem Tamam", final_msg)

            self.status_label.setText("Hazır.")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Hata", str(e))
            self.status_label.setText("Hata oluştu.")


# ──────────────────────────────────────────────
#  SEKME 4 — PDF Font Çıkarma
# ──────────────────────────────────────────────

class FontTab(QWidget):
    def __init__(self):
        super().__init__()
        self._fonts = []   # [{xref, name, type, ext, subset, size_kb, pages}]
        self._build_ui()

    def _build_ui(self):
        from PyQt5.QtWidgets import (QTableWidget, QTableWidgetItem, QHeaderView,
                                     QAbstractItemView, QMenu)
        from PyQt5.QtCore import Qt as QtCore_Qt
        layout = QVBoxLayout(self)

        # PDF seçimi
        top = QGridLayout()
        top.addWidget(QLabel("PDF Seç:"), 0, 0)
        self.pdf_entry = QLineEdit()
        self.pdf_entry.setPlaceholderText("Metin tabanlı bir PDF seçin...")
        top.addWidget(self.pdf_entry, 0, 1)
        top.addWidget(QPushButton("Gözat", clicked=self.browse_pdf), 0, 2)
        top.addWidget(QPushButton("Fontları Listele", clicked=self.list_fonts), 1, 1)
        layout.addLayout(top)

        # Font tablosu
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Font Adı", "Tür", "Format", "Alt Küme?", "Boyut", "Sayfalar"])

        # Tüm sütunlar kullanıcı tarafından sürüklenebilir (Interactive)
        hh = self.table.horizontalHeader()
        for col in range(6):
            hh.setSectionResizeMode(col, QHeaderView.Interactive)
        # Başlangıç genişlikleri
        self.table.setColumnWidth(0, 200)  # Font Adı
        self.table.setColumnWidth(1, 90)   # Tür
        self.table.setColumnWidth(2, 65)   # Format
        self.table.setColumnWidth(3, 90)   # Alt Küme
        self.table.setColumnWidth(4, 70)   # Boyut
        self.table.setColumnWidth(5, 120)  # Sayfalar
        # Son sütun kalan alanı doldursun
        hh.setStretchLastSection(True)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        # Sağ tık menüsü
        self.table.setContextMenuPolicy(QtCore_Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)

        # Kaydet butonu
        save_btn = QPushButton("Seçili Fontu Kaydet", clicked=self.save_font)
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet("background-color:#00796B; color:white; font-weight:bold;")
        layout.addWidget(save_btn)

        # Bilgi notu
        info = QLabel(
            "ℹ  Sütunları sürükleyerek genişletebilirsiniz. Sağ tık → Detayları Gör.\n"
            "   TTF/OTF → doğrudan kullanılabilir.  CFF → Type1 tabanlı, bazı uygulamalar açar."
        )
        info.setStyleSheet("color:#555; font-size:10px;")
        layout.addWidget(info)

        self.status_label = QLabel("Hazır.", styleSheet="color:blue;")
        layout.addWidget(self.status_label)

    def _show_context_menu(self, pos):
        from PyQt5.QtWidgets import QMenu, QDialog, QVBoxLayout, QLabel, QPushButton
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self._fonts):
            return

        menu = QMenu(self)
        action_detail = menu.addAction("🔍  Detayları Gör")
        action_save   = menu.addAction("💾  Bu Fontu Kaydet")
        action = menu.exec_(self.table.viewport().mapToGlobal(pos))

        if action == action_detail:
            self._show_font_detail(row)
        elif action == action_save:
            self.table.selectRow(row)
            self.save_font()

    def _show_font_detail(self, row):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFrame
        if row >= len(self._fonts):
            return
        f = self._fonts[row]
        pages_all = sorted(set(f["pages"]))

        dlg = QDialog(self)
        dlg.setWindowTitle("Font Detayı")
        dlg.setMinimumWidth(380)
        layout = QVBoxLayout(dlg)

        def add_row(label, value, bold=False):
            w = QLabel(f"<b>{label}:</b>  {value}")
            w.setWordWrap(True)
            if bold:
                w.setStyleSheet("font-size:12px;")
            layout.addWidget(w)

        add_row("Font Adı",    f["clean_name"], bold=True)
        add_row("Tür",         f["type"])
        add_row("Format",      f["ext"].upper())
        add_row("Alt Küme",    "⚠ Evet — sadece kullanılan karakterler gömülü" if f["subset"]
                               else "✔ Hayır — tam font")
        add_row("Boyut",       f"{f['size_kb']:.1f} KB" if f["has_data"] else "Gömülü Değil")
        add_row("Gömülü",      "✔ Evet, kaydedilebilir" if f["has_data"] else "✘ Hayır, sistemden sağlanıyor")
        add_row("Sayfa sayısı", str(len(pages_all)))
        add_row("Sayfalar",    ", ".join(map(str, pages_all)))

        # Ayırıcı çizgi
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        btn_row = QHBoxLayout()
        if f["has_data"]:
            save_btn = QPushButton("💾 Bu Fontu Kaydet")
            save_btn.clicked.connect(lambda: (dlg.accept(), self.table.selectRow(row), self.save_font()))
            btn_row.addWidget(save_btn)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec_()

    def browse_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF Seç", "", "PDF files (*.pdf)")
        if path:
            self.pdf_entry.setText(path)
            self.list_fonts()   # seçince otomatik listele

    def list_fonts(self):
        pdf_path = self.pdf_entry.text().strip()
        if not pdf_path or not os.path.exists(pdf_path):
            QMessageBox.warning(self, "Hata", "Geçerli bir PDF seçin!"); return

        try:
            import fitz
        except ImportError:
            QMessageBox.critical(self, "Eksik Paket",
                "PyMuPDF bulunamadı.\npip install pymupdf"); return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            doc = fitz.open(pdf_path)
            seen = {}   # xref → font bilgisi

            for page_num in range(len(doc)):
                for font in doc[page_num].get_fonts(full=True):
                    xref      = font[0]
                    font_type = font[2]
                    name      = font[3]
                    if xref in seen:
                        seen[xref]["pages"].append(page_num + 1)
                        continue
                    # Font verisini çıkar
                    try:
                        fd       = doc.extract_font(xref)
                        ext      = fd[1] if fd[1] else "?"
                        size_kb  = len(fd[3]) / 1024 if fd[3] else 0
                        has_data = bool(fd[3])
                    except Exception:
                        ext = "?"; size_kb = 0; has_data = False

                    seen[xref] = {
                        "xref":     xref,
                        "name":     name,
                        "type":     font_type,
                        "ext":      ext,
                        "subset":   "+" in name,
                        "size_kb":  size_kb,
                        "has_data": has_data,
                        "pages":    [page_num + 1],
                    }

            doc.close()
            self._fonts = list(seen.values())

            # Aynı isimli fontları birleştir (farklı xref ama aynı font adı)
            merged = {}
            for f in self._fonts:
                clean_name = f["name"].split("+")[-1]  # prefix'i kaldır
                key = clean_name
                if key not in merged:
                    merged[key] = dict(f)
                    merged[key]["clean_name"] = clean_name
                    merged[key]["xrefs"] = [f["xref"]]
                else:
                    merged[key]["xrefs"].append(f["xref"])
                    merged[key]["pages"].extend(f["pages"])
                    if f["size_kb"] > merged[key]["size_kb"]:
                        merged[key]["size_kb"]  = f["size_kb"]
                        merged[key]["xref"]     = f["xref"]
                        merged[key]["has_data"] = f["has_data"]

            self._fonts = list(merged.values())

            # Tabloyu doldur
            from PyQt5.QtWidgets import QTableWidgetItem
            from PyQt5.QtGui import QColor
            self.table.setRowCount(0)
            for f in self._fonts:
                r = self.table.rowCount()
                self.table.insertRow(r)
                pages_str = ", ".join(map(str, sorted(set(f["pages"]))[:6]))
                if len(set(f["pages"])) > 6: pages_str += "..."

                # CID tespiti: Type0 veya ext=="cid" ise CID font
                is_cid = (f["type"] == "Type0" or f["ext"].lower() in ("cid", "cff"))

                font_name_display = f["clean_name"]
                if is_cid:
                    font_name_display = "⚠ " + font_name_display

                self.table.setItem(r, 0, QTableWidgetItem(font_name_display))
                self.table.setItem(r, 1, QTableWidgetItem(f["type"]))
                fmt_display = f["ext"].upper()
                if is_cid:
                    fmt_display += " (CID)"
                self.table.setItem(r, 2, QTableWidgetItem(fmt_display))
                subset_text = "⚠ Alt Küme" if f["subset"] else "✔ Tam Font"
                self.table.setItem(r, 3, QTableWidgetItem(subset_text))
                self.table.setItem(r, 4, QTableWidgetItem(
                    f"{f['size_kb']:.1f} KB" if f["has_data"] else "Gömülü Değil"))
                self.table.setItem(r, 5, QTableWidgetItem(pages_str))

                # CID satırını hafif sarı ile vurgula
                if is_cid:
                    for col in range(6):
                        item = self.table.item(r, col)
                        if item:
                            item.setBackground(QColor(255, 252, 220))

                # CID bilgisini font dict'e kaydet (save_font'ta kullanmak için)
                f["is_cid"] = is_cid

            QApplication.restoreOverrideCursor()
            self.status_label.setText(
                f"{len(self._fonts)} benzersiz font bulundu.  "
                f"{'(Tümü alt küme — tam font içermeyebilir)' if all(f['subset'] for f in self._fonts) else ''}"
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Hata", str(e))

    def save_font(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Seçim Yok", "Lütfen listeden bir font seçin."); return
        if row >= len(self._fonts):
            return

        font_info = self._fonts[row]
        if not font_info["has_data"]:
            QMessageBox.warning(self, "Kayıt Edilemiyor",
                f"'{font_info['clean_name']}' fontu PDF'e gömülmemiş.\n"
                "Bu font sistemden veya harici kaynaktan sağlanmaktadır."); return

        pdf_path = self.pdf_entry.text().strip()
        try:
            import fitz
        except ImportError:
            QMessageBox.critical(self, "Eksik Paket", "pip install pymupdf"); return

        try:
            doc = fitz.open(pdf_path)
            fd  = doc.extract_font(font_info["xref"])
            doc.close()

            if not fd[3]:
                QMessageBox.warning(self, "Hata", "Font verisi okunamadı."); return

            ext      = fd[1] if fd[1] else "bin"
            is_cid   = font_info.get("is_cid", False)

            # CID font ise TTF dönüşümü teklif et
            if is_cid:
                reply = QMessageBox.question(
                    self, "CID Font Tespit Edildi",
                    f"'{font_info['clean_name']}' bir CID/CFF formatındadır.\n"
                    "Windows bu formatı doğrudan tanımaz.\n\n"
                    "fonttools ile TTF'e dönüştürülsün mü?\n"
                    "(Dönüştürme başarısız olursa orijinal format kaydedilir.)",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._save_as_ttf(font_info, fd[3], ext)
                    return

            def_name = f"{font_info['clean_name']}.{ext}"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Fontu Kaydet", def_name,
                f"Font (*.{ext});;Tüm dosyalar (*.*)"
            )
            if not save_path: return

            with open(save_path, "wb") as out:
                out.write(fd[3])

            size_kb = len(fd[3]) / 1024
            QMessageBox.information(self, "Kaydedildi",
                f"✔ {font_info['clean_name']}\n"
                f"Boyut: {size_kb:.1f} KB\n"
                f"Format: {ext.upper()}\n"
                f"Konum: {save_path}\n\n"
                f"{'⚠ Bu alt küme bir font — sadece kullanılan karakterler gömülmüştür.' if font_info['subset'] else '✔ Tam font.'}"
            )
            self.status_label.setText(f"Kaydedildi: {os.path.basename(save_path)}")

        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _save_as_ttf(self, font_info, font_data, orig_ext):
        """fonttools ile CID/CFF → TTF dönüşümü yapıp kaydeder."""
        try:
            from fontTools.ttLib import TTFont
            from fontTools import version as ft_version
        except ImportError:
            QMessageBox.critical(self, "Eksik Paket",
                "fonttools bulunamadı.\npip install fonttools\n\n"
                "Orijinal format kaydedilecek.")
            # Orijinal olarak kaydet
            self._save_raw(font_info, font_data, orig_ext)
            return

        import io
        clean = font_info["clean_name"]
        save_path, _ = QFileDialog.getSaveFileName(
            self, "TTF Olarak Kaydet", f"{clean}.ttf",
            "TrueType Font (*.ttf);;Tüm dosyalar (*.*)"
        )
        if not save_path: return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            buf = io.BytesIO(font_data)
            tt  = TTFont(buf)
            tt.save(save_path)
            QApplication.restoreOverrideCursor()
            size_kb = os.path.getsize(save_path) / 1024
            QMessageBox.information(self, "Dönüştürüldü ve Kaydedildi",
                f"✔ {clean}\n"
                f"CID/CFF → TTF dönüşümü başarılı!\n"
                f"Boyut: {size_kb:.1f} KB\n"
                f"Konum: {save_path}\n\n"
                f"{'⚠ Alt küme — sadece PDF içindeki karakterler mevcut.' if font_info['subset'] else '✔ Tam font.'}"
            )
            self.status_label.setText(f"TTF kaydedildi: {os.path.basename(save_path)}")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            # Dönüşüm başarısız → orijinal formatı kaydet
            reply = QMessageBox.warning(self, "Dönüşüm Başarısız",
                f"TTF dönüşümü sırasında hata oluştu:\n{e}\n\n"
                "Orijinal format olarak kaydedilsin mi?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._save_raw(font_info, font_data, orig_ext)

    def _save_raw(self, font_info, font_data, ext):
        """Dönüşüm yapılmadan orijinal font verisini kaydeder."""
        clean = font_info["clean_name"]
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Fontu Kaydet", f"{clean}.{ext}",
            f"Font (*.{ext});;Tüm dosyalar (*.*)"
        )
        if not save_path: return
        with open(save_path, "wb") as out:
            out.write(font_data)
        size_kb = len(font_data) / 1024
        QMessageBox.information(self, "Kaydedildi",
            f"✔ {clean}\nFormat: {ext.upper()}\nBoyut: {size_kb:.1f} KB\nKonum: {save_path}")
        self.status_label.setText(f"Kaydedildi: {os.path.basename(save_path)}")



# ──────────────────────────────────────────────
#  Ayarlar Yöneticisi (settings.json)
# ──────────────────────────────────────────────

import json

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "settings.json")

DEFAULT_SETTINGS = {
    "language":      "Türkçe",
    "jpeg_quality":  80,
    "jpeg_dpi":      300,
    "exif_sil":      False,
    "winrar_path":   "",
    "jpegoptim_path":"",
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Eksik anahtarları varsayılanlarla tamamla
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ayarlar kaydedilemedi: {e}")

# Global ayarlar nesnesi
APP_SETTINGS = load_settings()


# ──────────────────────────────────────────────
#  SEKME 5 — Çizgi Roman (CBR/CBZ)
# ──────────────────────────────────────────────

def extract_cbx(cbx_path, out_dir):
    """CBR veya CBZ dosyasını out_dir'e çıkarır. Sayfa listesi döner."""
    ext = os.path.splitext(cbx_path)[1].lower()
    os.makedirs(out_dir, exist_ok=True)

    if ext == ".cbz":
        import zipfile
        with zipfile.ZipFile(cbx_path, "r") as z:
            z.extractall(out_dir)

    elif ext == ".cbr":
        # Önce WinRAR dene
        winrar = APP_SETTINGS.get("winrar_path", "")
        unrar  = os.path.abspath("./unrar/unrar.exe")
        rar_exe = None
        if winrar and os.path.exists(winrar):
            rar_exe = winrar
        elif os.path.exists(unrar):
            rar_exe = unrar
        if rar_exe:
            si = make_startupinfo()
            subprocess.run([rar_exe, "e", cbx_path, out_dir, "-y"],
                           check=True, startupinfo=si)
        else:
            # py7zr fallback
            import py7zr
            with py7zr.SevenZipFile(cbx_path, mode="r") as z:
                z.extractall(out_dir)
    else:
        raise ValueError(f"Desteklenmeyen format: {ext}")

    # Çıkarılan görsel dosyaları doğal sırayla döndür
    imgs = []
    for ex in ["*.jpg","*.jpeg","*.png","*.webp","*.bmp","*.tiff","*.tif","*.gif"]:
        imgs.extend(glob.glob(os.path.join(out_dir, "**", ex), recursive=True))
        imgs.extend(glob.glob(os.path.join(out_dir, "**", ex.upper()), recursive=True))
    return natural_sort(imgs)


class CBRTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(30, 20, 30, 20)

        title = QLabel("Çizgi Roman İşlemleri")
        title.setStyleSheet("font-size:13px; font-weight:bold; color:#333;")
        layout.addWidget(title)

        # 3 büyük buton
        btn_style = """
            QPushButton {
                background-color: #283593;
                color: white;
                font-size: 13px;
                font-weight: bold;
                border-radius: 6px;
                padding: 18px;
            }
            QPushButton:hover { background-color: #3949AB; }
            QPushButton:pressed { background-color: #1A237E; }
        """

        btn1 = QPushButton("⚙  CBR/CBZ Optimizasyonu")
        btn2 = QPushButton("📄  PDF → CBR/CBZ")
        btn3 = QPushButton("📦  CBR/CBZ → PDF")
        for btn in [btn1, btn2, btn3]:
            btn.setStyleSheet(btn_style)
            btn.setMinimumHeight(70)
            layout.addWidget(btn)

        btn1.clicked.connect(self.optimize_cbx)
        btn2.clicked.connect(self.pdf_to_cbx)
        btn3.clicked.connect(self.cbx_to_pdf)

        layout.addStretch()

        self.status_label = QLabel("Hazır.", styleSheet="color:blue;")
        layout.addWidget(self.status_label)

    # ── Yardımcı: rapor dialogu ──
    def _show_report(self, title, msg, out_paths=None):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(480, 300)
        lay = QVBoxLayout(dlg)
        txt = QTextEdit(); txt.setReadOnly(True); txt.setPlainText(msg)
        lay.addWidget(txt)
        btn_row = QHBoxLayout()
        if out_paths:
            def open_folders():
                seen = set()
                for p in out_paths:
                    folder = os.path.dirname(p) if os.path.isfile(p) else p
                    if folder not in seen:
                        seen.add(folder)
                        try: os.startfile(folder)
                        except Exception: pass
            open_btn = QPushButton("📂  Dosya Konumunu Aç")
            open_btn.clicked.connect(open_folders)
            btn_row.addWidget(open_btn)
        close_btn = QPushButton("Kapat"); close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)
        dlg.exec_()

    # ── 1. CBR/CBZ Optimizasyonu ──
    def optimize_cbx(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "CBR/CBZ Seç", "",
            "Çizgi Roman (*.cbr *.cbz);;Tüm dosyalar (*.*)")
        if not files: return

        quality = APP_SETTINGS.get("jpeg_quality", 80)
        exif_sil = APP_SETTINGS.get("exif_sil", False)
        jpegoptim = APP_SETTINGS.get("jpegoptim_path", "")
        use_jpegoptim = bool(jpegoptim and os.path.exists(jpegoptim))

        results = []; errors = []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for src_path in files:
                base     = os.path.splitext(os.path.basename(src_path))[0]
                ext      = os.path.splitext(src_path)[1].lower()
                out_name = base + "_optimize" + ext
                out_path = os.path.join(os.path.dirname(src_path), out_name)
                tmp_in   = tempfile.mkdtemp()
                tmp_out  = tempfile.mkdtemp()
                try:
                    self.status_label.setText(f"Çıkarılıyor: {base}"); QApplication.processEvents()
                    imgs = extract_cbx(src_path, tmp_in)
                    if not imgs:
                        errors.append(f"✘ {base}: İçinde resim bulunamadı."); continue

                    self.status_label.setText(f"Optimize ediliyor: {base}"); QApplication.processEvents()
                    opt_imgs = []
                    for i, img_path in enumerate(imgs):
                        img_name = os.path.basename(img_path)
                        img_ext  = os.path.splitext(img_name)[1].lower()
                        out_img  = os.path.join(tmp_out, img_name)

                        if img_ext in (".jpg", ".jpeg"):
                            if use_jpegoptim:
                                si = make_startupinfo()
                                cmd = [jpegoptim, f"--max={quality}", "--dest", tmp_out]
                                if exif_sil: cmd.append("--strip-all")
                                cmd.append(img_path)
                                subprocess.run(cmd, check=True, startupinfo=si)
                            else:
                                # Pillow ile yeniden encode
                                with Image.open(img_path) as im:
                                    rgb = im.convert("RGB") if im.mode not in ("RGB","L") else im
                                    rgb.save(out_img, "JPEG", quality=quality,
                                             optimize=True,
                                             exif=b"" if exif_sil else im.info.get("exif", b""))
                        else:
                            shutil.copy2(img_path, out_img)
                        opt_imgs.append(out_img)

                    # Geri paketle
                    self.status_label.setText(f"Paketleniyor: {base}"); QApplication.processEvents()
                    import zipfile
                    if ext == ".cbz":
                        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                            for f in natural_sort(opt_imgs):
                                zf.write(f, os.path.basename(f))
                    else:  # cbr → cbz olarak kaydet (RAR oluşturmak için WinRAR şart)
                        winrar = APP_SETTINGS.get("winrar_path","")
                        if winrar and os.path.exists(winrar):
                            cbr_out = out_path
                            si = make_startupinfo()
                            cmd = [winrar, "a", "-ep", cbr_out] + natural_sort(opt_imgs)
                            subprocess.run(cmd, check=True, startupinfo=si)
                        else:
                            out_path = out_path.replace(".cbr", ".cbz")
                            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                                for f in natural_sort(opt_imgs):
                                    zf.write(f, os.path.basename(f))

                    orig_mb = os.path.getsize(src_path) / (1024*1024)
                    opt_mb  = os.path.getsize(out_path) / (1024*1024)
                    results.append(
                        f"✔ {base}: {orig_mb:.1f} MB → {opt_mb:.1f} MB "
                        f"(%{100-int(opt_mb/orig_mb*100)} küçüldü)")
                except Exception as e:
                    errors.append(f"✘ {base}: {e}")
                finally:
                    shutil.rmtree(tmp_in,  ignore_errors=True)
                    shutil.rmtree(tmp_out, ignore_errors=True)
        finally:
            QApplication.restoreOverrideCursor()

        msg = "\n".join(results)
        if errors: msg += "\n\n─── Hatalar ───\n" + "\n".join(errors)
        out_paths = [os.path.join(os.path.dirname(f), os.path.splitext(os.path.basename(f))[0] + "_optimize" + os.path.splitext(f)[1].lower()) for f in files]
        self._show_report("Optimizasyon Raporu", msg or "İşlem tamamlandı.", out_paths=out_paths)
        self.status_label.setText("Hazır.")

    # ── 2. PDF → CBR/CBZ ──
    def pdf_to_cbx(self):
        pdf_files, _ = QFileDialog.getOpenFileNames(
            self, "PDF Seç", "", "PDF (*.pdf);;Tüm dosyalar (*.*)")
        if not pdf_files: return

        fmt, ok = self._ask_cbx_format()
        if not ok: return

        try:
            import pikepdf
        except ImportError:
            QMessageBox.critical(self, "Eksik Paket", "pip install pikepdf"); return

        results  = []; errors = []; out_paths = []
        dpi      = APP_SETTINGS.get("jpeg_dpi", 300)
        quality  = APP_SETTINGS.get("jpeg_quality", 80)
        jpegoptim_path = APP_SETTINGS.get("jpegoptim_path", "")
        exif_sil       = APP_SETTINGS.get("exif_sil", False)
        use_jpegoptim  = bool(jpegoptim_path and os.path.exists(jpegoptim_path))
        si = make_startupinfo()

        def extract_page_images_pikepdf(pdf_path, quality):
            """
            pikepdf ile her sayfadaki gömülü görüntüyü çıkarır.
            - JPEG (DCTDecode): ham bytes doğrudan döner, decode/encode yok
            - Diğer: Pillow ile JPEG'e çevirir
            - Sayfa başına 1 görüntü yoksa None döner → pymupdf fallback
            Döner: [(dosya_adı, bytes), ...] veya None
            """
            import pikepdf
            pdf    = pikepdf.open(pdf_path)
            result = []
            ok     = True

            for page_num, page in enumerate(pdf.pages):
                page_images = list(page.images.items())
                if len(page_images) != 1:
                    ok = False; break
                name, raw_obj = page_images[0]
                try:
                    filt_name = str(raw_obj.get("/Filter", ""))
                    fname     = f"page-{page_num+1:05d}.jpeg"
                    if "DCTDecode" in filt_name:
                        # Ham JPEG — sıfır dönüşüm
                        data = raw_obj.read_raw_bytes()
                    else:
                        # PNG/CCITT vb. → Pillow ile JPEG
                        import io
                        pi      = pikepdf.PdfImage(raw_obj)
                        pil_img = pi.as_pil_image()
                        if pil_img.mode not in ("RGB", "L"):
                            pil_img = pil_img.convert("RGB")
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=quality, optimize=True)
                        data = buf.getvalue()
                    result.append((fname, data))
                except Exception:
                    ok = False; break

            pdf.close()
            return result if ok else None

        def extract_page_images_pymupdf(pdf_path, dpi, quality):
            """pymupdf ile her sayfayı render eder — fallback."""
            import fitz, io
            doc    = fitz.open(pdf_path)
            mat    = fitz.Matrix(dpi / 72, dpi / 72)
            result = []
            for page_num in range(len(doc)):
                pix   = doc[page_num].get_pixmap(matrix=mat, alpha=False)
                fname = f"page-{page_num+1:05d}.jpeg"
                data  = pix.tobytes("jpeg")
                result.append((fname, data))
            doc.close()
            return result

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for pdf_path in pdf_files:
                base     = os.path.splitext(os.path.basename(pdf_path))[0]
                out_ext  = f".{fmt}"
                out_path = os.path.join(os.path.dirname(pdf_path), base + out_ext)
                try:
                    # Yöntem 1: pikepdf doğrudan (hızlı, boyut korur)
                    self.status_label.setText(f"Görüntüler çıkarılıyor: {base}"); QApplication.processEvents()
                    pages  = extract_page_images_pikepdf(pdf_path, quality)
                    method = "pikepdf (doğrudan)"

                    # Yöntem 2: pymupdf fallback
                    if pages is None:
                        self.status_label.setText(f"Render ediliyor: {base}"); QApplication.processEvents()
                        try:
                            pages  = extract_page_images_pymupdf(pdf_path, dpi, quality)
                            method = f"pymupdf ({dpi}dpi)"
                        except ImportError:
                            errors.append(f"✘ {base}: Hem pikepdf hem pymupdf başarısız."); continue

                    if not pages:
                        errors.append(f"✘ {base}: Görüntü çıkarılamadı."); continue

                    # jpegoptim: geçici dosya gerekiyor, varsa uygula
                    if use_jpegoptim:
                        self.status_label.setText(f"jpegoptim: {base}"); QApplication.processEvents()
                        tmp_dir = tempfile.mkdtemp()
                        try:
                            new_pages = []
                            for fname, data in pages:
                                tmp_f = os.path.join(tmp_dir, fname)
                                with open(tmp_f, "wb") as f: f.write(data)
                                cmd_jo = [jpegoptim_path, f"--max={quality}", "--overwrite"]
                                if exif_sil: cmd_jo.append("--strip-all")
                                cmd_jo.append(tmp_f)
                                subprocess.run(cmd_jo, check=True, startupinfo=si)
                                with open(tmp_f, "rb") as f: data = f.read()
                                new_pages.append((fname, data))
                            pages = new_pages
                        finally:
                            shutil.rmtree(tmp_dir, ignore_errors=True)

                    # Paketle — doğrudan bellekten ZIP/CBR
                    self.status_label.setText(f"Paketleniyor ({fmt.upper()}): {base}"); QApplication.processEvents()
                    import zipfile
                    winrar = APP_SETTINGS.get("winrar_path", "")

                    if fmt == "cbz":
                        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zf:
                            for fname, data in pages:
                                zf.writestr(fname, data)
                    else:  # cbr
                        if winrar and os.path.exists(winrar):
                            # WinRAR gerçek RAR formatı için — geçici dizin gerekli
                            tmp_dir = tempfile.mkdtemp()
                            try:
                                tmp_files = []
                                for fname, data in pages:
                                    p = os.path.join(tmp_dir, fname)
                                    with open(p, "wb") as f: f.write(data)
                                    tmp_files.append(p)
                                cmd = [winrar, "a", "-ep", "-ibck", out_path] + tmp_files
                                subprocess.run(cmd, check=True, startupinfo=si)
                            finally:
                                shutil.rmtree(tmp_dir, ignore_errors=True)
                        else:
                            # WinRAR yoksa ZIP container ile .cbr yaz
                            # (tüm okuyucular ZIP tabanlı CBR'yi açar)
                            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zf:
                                for fname, data in pages:
                                    zf.writestr(fname, data)

                    size_mb  = os.path.getsize(out_path) / (1024*1024)
                    opt_note = " + jpegoptim" if use_jpegoptim else ""
                    results.append(
                        f"✔ {base} → {os.path.basename(out_path)} "
                        f"({size_mb:.1f} MB, {len(pages)} sayfa, {method}{opt_note})")
                    out_paths.append(out_path)
                except Exception as e:
                    errors.append(f"✘ {base}: {e}")
        finally:
            QApplication.restoreOverrideCursor()

        msg = "\n".join(results)
        if errors: msg += "\n\n─── Hatalar/Uyarılar ───\n" + "\n".join(errors)
        self._show_report("PDF → CBR/CBZ Raporu", msg or "İşlem tamamlandı.", out_paths=out_paths)
        self.status_label.setText("Hazır.")

    # ── 3. CBR/CBZ → PDF ──
    def cbx_to_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "CBR/CBZ Seç", "",
            "Çizgi Roman (*.cbr *.cbz);;Tüm dosyalar (*.*)")
        if not files: return

        try:
            import img2pdf
        except ImportError:
            QMessageBox.critical(self, "Eksik Paket", "pip install img2pdf"); return

        quality = APP_SETTINGS.get("jpeg_quality", 80)
        dpi     = APP_SETTINGS.get("jpeg_dpi", 300)
        results = []; errors = []; out_paths = []

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for src_path in files:
                base     = os.path.splitext(os.path.basename(src_path))[0]
                out_path = os.path.join(os.path.dirname(src_path), base + ".pdf")
                tmp_dir  = tempfile.mkdtemp()
                try:
                    self.status_label.setText(f"Çıkarılıyor: {base}"); QApplication.processEvents()
                    imgs = extract_cbx(src_path, tmp_dir)
                    if not imgs:
                        errors.append(f"✘ {base}: İçinde resim bulunamadı."); continue

                    self.status_label.setText(f"PDF oluşturuluyor: {base}"); QApplication.processEvents()

                    # img2pdf ile birleştir
                    pdf_data = img2pdf.convert(imgs)
                    with open(out_path, "wb") as f:
                        f.write(pdf_data)

                    size_mb = os.path.getsize(out_path) / (1024*1024)
                    results.append(f"✔ {base} → {base}.pdf ({size_mb:.1f} MB, {len(imgs)} sayfa)")
                    out_paths.append(out_path)
                except Exception as e:
                    errors.append(f"✘ {base}: {e}")
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
        finally:
            QApplication.restoreOverrideCursor()

        msg = "\n".join(results)
        if errors: msg += "\n\n─── Hatalar ───\n" + "\n".join(errors)
        self._show_report("CBR/CBZ → PDF Raporu", msg or "İşlem tamamlandı.", out_paths=out_paths)
        self.status_label.setText("Hazır.")

    def _ask_cbx_format(self):
        """CBZ mi CBR mi? diye sorar."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle("Çıktı Formatı")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Çıktı formatını seçin:"))
        result = [None]
        btn_row = QHBoxLayout()
        for fmt in ["cbz", "cbr"]:
            b = QPushButton(fmt.upper())
            b.setMinimumWidth(80)
            b.clicked.connect(lambda _, f=fmt: (result.__setitem__(0, f), dlg.accept()))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)
        dlg.exec_()
        return result[0], result[0] is not None


# ──────────────────────────────────────────────
#  SEKME 6 — Ayarlar (⚙)
# ──────────────────────────────────────────────

class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        grid   = QGridLayout()
        grid.setColumnMinimumWidth(0, 160)
        row = 0

        # Dil
        grid.addWidget(QLabel("Dil:"), row, 0)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Türkçe", "English"])
        self.lang_combo.setCurrentText(APP_SETTINGS.get("language", "Türkçe"))
        grid.addWidget(self.lang_combo, row, 1); row += 1

        # JPEG Kalitesi
        grid.addWidget(QLabel("JPEG Kalitesi:"), row, 0)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(APP_SETTINGS.get("jpeg_quality", 80))
        self.quality_spin.setSuffix("%")
        self.quality_spin.setFixedWidth(80)
        grid.addWidget(self.quality_spin, row, 1); row += 1

        # JPEG DPI
        grid.addWidget(QLabel("JPEG DPI:"), row, 0)
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["72","96","150","200","300","400","600"])
        self.dpi_combo.setCurrentText(str(APP_SETTINGS.get("jpeg_dpi", 300)))
        grid.addWidget(self.dpi_combo, row, 1); row += 1

        # EXIF Sil
        grid.addWidget(QLabel("EXIF Sil:"), row, 0)
        self.exif_combo = QComboBox()
        self.exif_combo.addItems(["Hayır", "Evet"])
        self.exif_combo.setCurrentIndex(1 if APP_SETTINGS.get("exif_sil", False) else 0)
        grid.addWidget(self.exif_combo, row, 1); row += 1

        # WinRAR yolu
        grid.addWidget(QLabel("WinRAR Lokasyonu:"), row, 0)
        wr_widget = QWidget(); wr_layout = QHBoxLayout(wr_widget); wr_layout.setContentsMargins(0,0,0,0)
        self.winrar_entry = QLineEdit(APP_SETTINGS.get("winrar_path",""))
        self.winrar_entry.setPlaceholderText("C:\\Program Files\\WinRAR\\WinRAR.exe")
        wr_layout.addWidget(self.winrar_entry)
        wr_layout.addWidget(QPushButton("Göz At", clicked=self._browse_winrar))
        grid.addWidget(wr_widget, row, 1); row += 1

        # jpegoptim yolu
        grid.addWidget(QLabel("jpegoptim.exe:"), row, 0)
        jo_widget = QWidget(); jo_layout = QHBoxLayout(jo_widget); jo_layout.setContentsMargins(0,0,0,0)
        self.jpegoptim_entry = QLineEdit(APP_SETTINGS.get("jpegoptim_path",""))
        self.jpegoptim_entry.setPlaceholderText("./jpegoptim/jpegoptim.exe  (boşsa Pillow kullanılır)")
        jo_layout.addWidget(self.jpegoptim_entry)
        jo_layout.addWidget(QPushButton("Göz At", clicked=self._browse_jpegoptim))
        grid.addWidget(jo_widget, row, 1); row += 1

        layout.addLayout(grid)
        layout.addSpacing(10)

        # ── Sekme Düzenleme ──────────────────────
        tab_group_label = QLabel("Sekmeleri Düzenle:")
        tab_group_label.setStyleSheet("font-weight:bold; margin-top:6px;")
        layout.addWidget(tab_group_label)

        from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
        from PyQt5.QtCore import Qt as QtC

        self.TAB_DEFS = [
            ("📄  PDF İşleme",   "pdf"),
            ("🖼️  Resim İşleme", "image"),
            ("🔓  Şifre Çöz",    "decrypt"),
            ("🔤  PDF Font",     "font"),
            ("📦  Çizgi Roman",  "cbr"),
        ]
        saved_order   = APP_SETTINGS.get("tab_order",   [d[1] for d in self.TAB_DEFS])
        saved_visible = APP_SETTINGS.get("tab_visible", {d[1]: True for d in self.TAB_DEFS})

        # Kaydedilen sıraya göre sırala
        key_to_def = {k: (label, k) for label, k in self.TAB_DEFS}
        ordered = []
        for k in saved_order:
            if k in key_to_def: ordered.append(key_to_def[k])
        for label, k in self.TAB_DEFS:
            if k not in saved_order: ordered.append((label, k))

        tab_ctrl_widget = QWidget()
        tab_ctrl_layout = QHBoxLayout(tab_ctrl_widget)
        tab_ctrl_layout.setContentsMargins(0,0,0,0)

        self.tab_list = QListWidget()
        self.tab_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.tab_list.setFixedHeight(130)
        self.tab_checks = {}

        for label, key in ordered:
            item = QListWidgetItem(label)
            item.setData(QtC.UserRole, key)
            item.setFlags(item.flags() | QtC.ItemIsUserCheckable)
            item.setCheckState(QtC.Checked if saved_visible.get(key, True) else QtC.Unchecked)
            self.tab_list.addItem(item)

        tab_ctrl_layout.addWidget(self.tab_list)

        # Yukarı/Aşağı butonları
        arrows = QVBoxLayout()
        up_btn = QPushButton("▲"); up_btn.setFixedWidth(30)
        dn_btn = QPushButton("▼"); dn_btn.setFixedWidth(30)
        up_btn.clicked.connect(self._tab_move_up)
        dn_btn.clicked.connect(self._tab_move_down)
        arrows.addStretch(); arrows.addWidget(up_btn); arrows.addWidget(dn_btn); arrows.addStretch()
        tab_ctrl_layout.addLayout(arrows)
        layout.addWidget(tab_ctrl_widget)

        info_lbl = QLabel("ℹ  Sıralamak için sürükleyin veya ▲▼ kullanın. ✓ görünür, □ gizli.\n   Ayarlar sekmesi her zaman en sağda sabit kalır.")
        info_lbl.setStyleSheet("color:#777; font-size:9px;")
        layout.addWidget(info_lbl)
        layout.addSpacing(6)

        # Kaydet butonu
        save_btn = QPushButton("Ayarları Kaydet")
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet("background-color:#455A64; color:white; font-weight:bold;")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        # Program versiyonu
        ver_lbl = QLabel("ReinventFK v4.6")
        ver_lbl.setStyleSheet("color:#999; font-size:10px;")
        ver_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(ver_lbl)

        layout.addStretch()

    def _tab_move_up(self):
        row = self.tab_list.currentRow()
        if row > 0:
            item = self.tab_list.takeItem(row)
            self.tab_list.insertItem(row - 1, item)
            self.tab_list.setCurrentRow(row - 1)

    def _tab_move_down(self):
        row = self.tab_list.currentRow()
        if row < self.tab_list.count() - 1:
            item = self.tab_list.takeItem(row)
            self.tab_list.insertItem(row + 1, item)
            self.tab_list.setCurrentRow(row + 1)

    def _browse_winrar(self):
        p, _ = QFileDialog.getOpenFileName(self, "WinRAR.exe Seç", "", "Exe (*.exe)")
        if p: self.winrar_entry.setText(p)

    def _browse_jpegoptim(self):
        p, _ = QFileDialog.getOpenFileName(self, "jpegoptim.exe Seç", "", "Exe (*.exe)")
        if p: self.jpegoptim_entry.setText(p)

    def _save(self):
        from PyQt5.QtCore import Qt as QtC
        APP_SETTINGS["language"]       = self.lang_combo.currentText()
        APP_SETTINGS["jpeg_quality"]   = self.quality_spin.value()
        APP_SETTINGS["jpeg_dpi"]       = int(self.dpi_combo.currentText())
        APP_SETTINGS["exif_sil"]       = self.exif_combo.currentIndex() == 1
        APP_SETTINGS["winrar_path"]    = self.winrar_entry.text().strip()
        APP_SETTINGS["jpegoptim_path"] = self.jpegoptim_entry.text().strip()

        # Sekme sırası ve görünürlük
        order   = []
        visible = {}
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            key  = item.data(QtC.UserRole)
            order.append(key)
            visible[key] = (item.checkState() == QtC.Checked)
        APP_SETTINGS["tab_order"]   = order
        APP_SETTINGS["tab_visible"] = visible
        save_settings(APP_SETTINGS)
        QMessageBox.information(self, "Kaydedildi",
            "✔ Ayarlar kaydedildi.\nSekme düzenlemesi bir sonraki açılışta uygulanır.")


# ──────────────────────────────────────────────
#  Ana Pencere
# ──────────────────────────────────────────────

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReinventFK v4.6")
        self.resize(580, 420)

        # Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "icon.ico")
        if os.path.exists(icon_path):
            from PyQt5.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))

        # Tab tanımları — key → (label, widget sınıfı)
        TAB_MAP = {
            "pdf":     ("📄  PDF İşleme",   PDFTab),
            "image":   ("🖼️  Resim İşleme", ImageTab),
            "decrypt": ("🔓  Şifre Çöz",    DecryptTab),
            "font":    ("🔤  PDF Font",      FontTab),
            "cbr":     ("📦  Çizgi Roman",   CBRTab),
        }

        saved_order   = APP_SETTINGS.get("tab_order",   list(TAB_MAP.keys()))
        saved_visible = APP_SETTINGS.get("tab_visible", {k: True for k in TAB_MAP})

        tabs = QTabWidget()

        # Kaydedilen sıraya göre sekmeleri ekle, gizliler atlanır
        added_keys = []
        for key in saved_order:
            if key in TAB_MAP and saved_visible.get(key, True):
                label, cls = TAB_MAP[key]
                tabs.addTab(cls(), label)
                added_keys.append(key)

        # Sırada olmayan ama visible olan sekmeleri sona ekle
        for key, (label, cls) in TAB_MAP.items():
            if key not in added_keys and saved_visible.get(key, True):
                tabs.addTab(cls(), label)

        # Ayarlar her zaman en sona
        tabs.addTab(SettingsTab(), "⚙")
        tabs.tabBar().setTabToolTip(tabs.count() - 1, "Ayarlar")

        self.setCentralWidget(tabs)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainApp()
    w.show()
    sys.exit(app.exec_())
