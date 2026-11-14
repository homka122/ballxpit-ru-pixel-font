# BALL x PIT: пиксельный шрифт для русского языка (Ark Pixel 12px, OFL)
# Подменяет шрифт "NotoSerif-Regular SDF" в Balls_Data/resources.assets.
import os, sys, json, shutil, re, traceback, winreg

FONT_NAME = "NotoSerif-Regular SDF"
MARK = b"Ark Pixel"  # имя семейства нового шрифта, в оригинальном файле его нет
STEAM_FIX = "Steam: ПКМ по игре > Свойства > Установленные файлы > Проверить целостность файлов игры."
REPORT = "Напиши в комментариях к руководству в Steam или в Issues на github.com/homka122/ballxpit-ru-pixel-font."


class Fail(Exception):
    pass


def here():
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))


def data_path(name):
    return os.path.join(getattr(sys, "_MEIPASS", here()), "data", name)


def steam_libraries():
    roots = [r"C:\Program Files (x86)\Steam"]
    for hive, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                           (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
        try:
            with winreg.OpenKey(hive, key) as k:
                roots.append(winreg.QueryValueEx(k, val)[0])
        except OSError:
            pass
    libs = []
    for r in roots:
        libs.append(r)
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            with open(vdf, encoding="utf8", errors="ignore") as f:
                libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
    return libs


def find_data_dir(path=None):
    cands = [path, os.path.join(path, "Balls_Data")] if path else []
    cands += [os.path.join(here(), "Balls_Data"), os.path.join(here(), "..", "Balls_Data")]
    cands += [os.path.join(lib, "steamapps", "common", "BALLxPIT", "Balls_Data") for lib in steam_libraries()]
    for c in cands:
        if os.path.isfile(os.path.join(c, "resources.assets")):
            return os.path.normpath(c)
    return None


def install(data_dir):
    import UnityPy
    from PIL import Image
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode

    res = os.path.join(data_dir, "resources.assets")
    orig = res + ".orig"
    with open(res, "rb") as f:  # читаем в память, чтобы файл не оставался открытым
        current = f.read()
    base = current
    if MARK in current:  # уже стоит какая-то версия мода: собираем заново из оригинала
        if not os.path.isfile(orig):
            raise Fail("Мод уже стоит, но копии оригинального файла нет. Верни его через " + STEAM_FIX
                       + " Потом запусти программу ещё раз.")
        with open(orig, "rb") as f:
            base = f.read()
    print("Ставлю шрифт, это может занять до минуты. Не закрывай окно.")

    with open(data_path("fontasset_nodes.json"), encoding="utf8") as f:
        nd = TypeTreeNode.from_list([TypeTreeNode(n["m_Level"], n["m_Type"], n["m_Name"], 0, 0, m_MetaFlag=n["m_MetaFlag"])
                                     for n in json.load(f)])
    with open(data_path("font_data.json"), encoding="utf8") as f:
        data = json.load(f)
    af = list(UnityPy.load(base).files.values())[0]

    obj = next((o for o in af.objects.values()
                if o.type.name == "MonoBehaviour" and o.read(check_read=False).m_Name == FONT_NAME), None)
    if obj is None:
        raise Fail(f"Не нашёл в игре шрифт {FONT_NAME}. Скорее всего, игра обновилась. Файлы игры не изменены. " + REPORT)
    raw = obj.get_raw_data()
    tt = obj.read_typetree(nodes=nd)
    obj.save_typetree(tt, nodes=nd)
    if obj.get_raw_data() != raw or tt["m_AtlasPadding"] != data["m_AtlasPadding"] or tt["m_AtlasTextures"][0]["m_FileID"] != 0:
        raise Fail("Шрифт в игре устроен не так, как ожидалось. Скорее всего, игра обновилась. Файлы игры не изменены. " + REPORT)

    for k in ("m_FaceInfo", "m_GlyphTable", "m_CharacterTable", "m_UsedGlyphRects", "m_AtlasWidth", "m_AtlasHeight"):
        tt[k] = data[k]
    tt["m_FreeGlyphRects"] = []
    tt["m_CreationSettings"].update(atlasWidth=data["m_AtlasWidth"], atlasHeight=data["m_AtlasHeight"],
                                    pointSize=int(data["m_FaceInfo"]["m_PointSize"]),
                                    characterSequence=data["characterSequence"])
    for k, v in tt["m_FontFeatureTable"].items():
        if isinstance(v, list):
            tt["m_FontFeatureTable"][k] = []
    obj.save_typetree(tt, nodes=nd)

    tex_id = tt["m_AtlasTextures"][0]["m_PathID"]
    tex = af.objects[tex_id].read()
    tex.set_image(Image.open(data_path("atlas.png")).convert("RGBA"), target_format=tex.m_TextureFormat)
    tex.save()

    size = {"_TextureWidth": data["m_AtlasWidth"], "_TextureHeight": data["m_AtlasHeight"]}
    for o in af.objects.values():
        if o.type.name != "Material":
            continue
        m = o.read()
        if any(k == "_MainTex" and v.m_Texture.m_FileID == 0 and v.m_Texture.m_PathID == tex_id
               for k, v in m.m_SavedProperties.m_TexEnvs):
            fl = m.m_SavedProperties.m_Floats
            for i, (k, _) in enumerate(fl):
                if k in size:
                    fl[i] = (k, float(size[k]))
            m.save()

    blob = af.save()
    if blob == current:
        print("Шрифт уже установлен, делать ничего не нужно.")
        return
    if base is current:
        shutil.copy2(res, orig)
    with open(res, "wb") as f:  # пишем поверх: os.replace в Program Files упирается в права
        f.write(blob)
    print("Готово, шрифт установлен. Оригинальный файл сохранён как resources.assets.orig.")


def uninstall(data_dir):
    res = os.path.join(data_dir, "resources.assets")
    orig = res + ".orig"
    with open(res, "rb") as f:
        if MARK not in f.read():
            print("Мод не установлен: в игре сейчас оригинальный шрифт.")
            return
    if not os.path.isfile(orig):
        raise Fail("Не нашёл копию оригинального файла. Верни его через " + STEAM_FIX)
    shutil.copyfile(orig, res)
    print("Готово, вернул оригинальный шрифт.")


def main():
    print("BALL x PIT: пиксельный шрифт для русского языка\n")
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    data_dir = find_data_dir(args[0] if args else None)
    if not data_dir:
        print("Не нашёл игру автоматически.")
        print("Открой её папку: Steam > ПКМ по игре > Управление > Просмотреть локальные файлы,")
        print("кликни в адресную строку проводника и скопируй путь.")
        data_dir = find_data_dir(input("Вставь путь сюда (правой кнопкой мыши) и нажми Enter: ").strip().strip('"'))
        if not data_dir:
            raise Fail("В этой папке нет игры. Нужна папка, где лежит Balls.exe. Запусти программу ещё раз.")
    print("Папка игры:", os.path.dirname(data_dir))
    try:
        with open(os.path.join(data_dir, "resources.assets"), "r+b"):
            pass
    except PermissionError:
        raise Fail("Не получается записать файл игры. Закрой игру и запусти программу ещё раз."
                   " Если игра и так закрыта, запусти программу от имени администратора.")
    (uninstall if "--uninstall" in sys.argv else install)(data_dir)


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Fail as e:
        print("\n" + str(e))
        code = 1
    except Exception:
        log = os.path.join(here(), "error.log")
        try:
            with open(log, "w", encoding="utf8") as f:
                traceback.print_exc(file=f)
        except OSError:
            traceback.print_exc()
            log = "окна выше"
        print("\nЧто-то пошло не так. " + REPORT + " Приложи текст из " + log + ".")
        print("Если игра перестала запускаться, верни файлы через " + STEAM_FIX)
        code = 1
    if getattr(sys, "frozen", False):
        try:
            input("\nНажми Enter, чтобы закрыть окно...")
        except EOFError:
            pass
    sys.exit(code)
