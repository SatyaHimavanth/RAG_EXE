from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import os
import llama_cpp

project_root = Path(os.getcwd())

hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("chromadb")
    + [
        "chromadb.telemetry",
        "chromadb.telemetry.product",
        "chromadb.telemetry.product.posthog",
    ]
)

llama_cpp_dir = Path(llama_cpp.__file__).parent
llama_cpp_lib = llama_cpp_dir / "lib"

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    hiddenimports=hiddenimports,
    datas=[
        (str(project_root / "static"), "static"),
    ],
    binaries=[
        (str(llama_cpp_lib), "llama_cpp/lib"),
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="chatbot",
    console=True,
)
