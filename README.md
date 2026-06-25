# TNS Converter

Convierte archivos `.tns` de la calculadora **TI-Nspire** a formatos editables y viceversa.
Un solo archivo, abre una interfaz web en tu navegador. Funciona en **Windows**, **macOS** y **Linux**.

- **Notas** (`.tns`) ↔ Texto (`.txt`)
- **Hojas de cálculo** (`.tns`) ↔ Excel (`.xlsx`) / CSV (`.csv`)
- Preserva fórmulas (`=A1+B1`, `=SUM(...)`, etc.)

## Descarga

Ve a [Releases](https://github.com/hatysquarepants0310/tns-convert/releases/tag/latest) y descarga el ejecutable para tu sistema:

| Sistema | Archivo |
|---------|---------|
| Windows | `TNS_Converter_Windows.exe` |
| macOS | `TNS_Converter_Mac` |
| Linux | `TNS_Converter_Linux` |

> **macOS:** la primera vez haz click derecho → "Abrir" en vez de doble click.

## Uso con Python

Si prefieres correrlo como script:

```bash
pip install cryptography
python3 tns_converter_app.py
```

Se abre automáticamente en tu navegador. No necesitas internet — todo corre en tu máquina.

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

## Licencia

[MIT](LICENSE)
