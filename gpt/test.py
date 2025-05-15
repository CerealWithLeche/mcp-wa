import os

PATH_TO_SRC = os.getenv("PATH_TO_SRC", "/home/luis-ignacio-zamora/whatsapp-mcp")
print(f"PATH_TO_SRC is set to: {PATH_TO_SRC}")

# Verifica si existe
if not os.path.exists(PATH_TO_SRC):
    print("⚠️ La ruta especificada no existe.")
else:
    print("✅ La ruta existe.")
