# PyMuPDF Installation Guide

PyMuPDF requires compilation and needs C compiler. Two options:

## Option 1: Install Build Tools (Recommended)

```bash
# Install GCC and development tools
sudo yum install gcc gcc-c++ make python3-devel -y

# Now install PyMuPDF
pip3 install --user PyMuPDF==1.24.5
```

## Option 2: Use Pre-compiled Wheel

Try installing without version constraint to get latest pre-built:

```bash
pip3 install --user PyMuPDF
```

## Option 3: Alternative Parser (if PyMuPDF fails)

If you can't install PyMuPDF, we can switch to pypdf or pdfplumber:

```bash
pip3 install --user pypdf pdfplumber
```

Then modify `app/sop/parser.py` to use alternative library.

## Current Status

Run one of the options above, then test:

```bash
python3 -c "import fitz; print('✅ PyMuPDF installed:', fitz.__version__)"
```
