# Tests

The public repository does not include TI-Nspire `.tns` documents or TI DLLs.

To validate locally, place your own `.tns` files in a folder and run:

```powershell
python tnstools.py --validate path\to\folder
```

If TI-Nspire Student Software is installed, run the stronger compatibility
check:

```powershell
python tnstools.py --validate path\to\folder --validate-phoenix
```

Both commands use temporary files and discard intermediate XML/TNS outputs.
