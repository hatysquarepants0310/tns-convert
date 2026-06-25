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

## Licencia

[MIT](LICENSE)
