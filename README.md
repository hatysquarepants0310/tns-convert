# TNS Converter

Convierte archivos `.tns` de la calculadora **TI-Nspire** a formatos editables y viceversa.
Un solo archivo, abre una interfaz web en tu navegador. Funciona en **Windows**, **macOS** y **Linux**.

- **Notas** (`.tns`) ↔ Texto (`.txt`)
- **Hojas de cálculo** (`.tns`) ↔ Excel (`.xlsx`) / CSV (`.csv`)
- Preserva fórmulas (`=A1+B1`, `=SUM(...)`, etc.)

## Inicio rápido

```bash
python3 tns_converter_app.py
```

Se abre automáticamente en tu navegador. No necesitas internet — todo corre en tu máquina.

## Requisitos

- **Python 3.10+**
- **cryptography** (viene preinstalada en la mayoría de sistemas Linux/Mac)

```bash
# Si no tienes cryptography:
pip install cryptography
```

## Instalación

```bash
git clone https://github.com/hatysquarepants0310/tns-convert.git
cd tns-convert
python3 tns_converter_app.py
```

Es un solo archivo. También puedes descargar únicamente `tns_converter_app.py` y ejecutarlo.

## Qué puedes hacer

| Acción | Cómo |
|--------|------|
| Editar notas de la calculadora | Arrastra el `.tns` → edita el texto → descarga el nuevo `.tns` |
| Editar hojas de cálculo | Arrastra el `.tns` → edita la tabla → descarga `.tns` |
| Pasar un Excel a la calculadora | Arrastra tu `.xlsx` → descarga como `.tns` |
| Exportar datos de la calculadora | Arrastra el `.tns` → descarga como `.xlsx` o `.csv` |
| Crear notas desde cero | Click en "+ Crear notas nuevas" |
| Crear hoja de cálculo desde cero | Click en "+ Crear hoja de cálculo nueva" |

## Fórmulas

Las fórmulas de Excel se convierten a fórmulas de la calculadora:

```
=A1+B1      →  A1+B1       (la TI-Nspire no usa el signo =)
=SUM(A1:A5) →  SUM(A1:A5)
```

Al exportar de `.tns` a `.xlsx`, las fórmulas se preservan como fórmulas de Excel.

## Archivos de ejemplo

- `leyes.tns` — ejemplo de notas
- `exel.tns` — ejemplo de hoja de cálculo

---

## Herramientas avanzadas (TnsTools)

Este repositorio también incluye las herramientas de bajo nivel para trabajar directamente con el XML interno de los archivos `.tns`:

### Decodificar `.tns` a XML

```bash
python tnstools.py -tns archivo.tns
```

Crea una carpeta con los XML extraídos (`Document.xml`, `Problem1.xml`, etc.).

### Reconstruir `.tns` desde XML

```bash
python tnstools.py -xml archivo.tns.xml -out reconstruido.tns
```

### Cómo funciona internamente

```
Decode:  .tns → method 13 → 3DES decrypt → deflate → TIXC → XML
Encode:  XML → TIXC → deflate → 3DES encrypt → method 13 → .tns
```

Métodos de compresión soportados:
- **Method 0** — sin compresión
- **Method 8** — deflate
- **Method 13** — envelope propietario de TI (3DES + TIXC)

### Opciones de TnsTools

```
python tnstools.py -tns FILE          Decodificar .tns a XML
python tnstools.py -xml DIR           Construir .tns desde XML
python tnstools.py --validate [DIR]   Validar archivos .tns con roundtrip
                   -out PATH          Ruta de salida
                   --list             Mostrar entradas
                   --verify           Verificar XML después de reconstruir
                   --artifacts        Escribir TIXC y manifiesto de diagnóstico
```

## Compatibilidad

Probado con documentos de:
- Program Editor UDFs
- Scratchpad / historial
- Lists & Spreadsheet
- DataGrapher / gráficas
- ScriptApp / Lua
- Documentos CX y CX II

## Créditos

Construido sobre [TnsTools](https://github.com/MaksimirKurtov/TnsTools) (MIT) para el manejo del cifrado 3DES propietario de TI.

## Licencia

[MIT](LICENSE)
