# Собирает data/ для патчера: SDF-атлас и таблицы глифов из пиксельного TTF.
# python build.py <папка игры> <шрифт.ttf> <папка data> [resources.assets]
# pip install UnityPy TypeTreeGeneratorAPI fonttools scipy
# Если игра уже пропатчена, последним аргументом укажи resources.assets.orig.
import os, sys, json
import numpy as np
import UnityPy
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt as edt
from fontTools.ttLib import TTFont
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from UnityPy.helpers.TypeTreeNode import TypeTreeNode

GAME, TTF, OUT = sys.argv[1:4]
RES = sys.argv[4] if len(sys.argv) > 4 else os.path.join(GAME, "Balls_Data", "resources.assets")
PT = 72          # размер растра: у Ark Pixel 12px это ровно 6 текселей на пиксель
SPREAD = 9.0     # = _GradientScale в материале шрифта (padding + 1)
SCALE = 0.72     # подгонка под размер Noto Serif в игре
EXTRA = "–—‘’“”„…№•«»×Ґґ"

# структура TMP_FontAsset берётся из GameAssembly.dll
af = list(UnityPy.load(RES).files.values())[0]
gen = TypeTreeGenerator(af.unity_version)
with open(os.path.join(GAME, "GameAssembly.dll"), "rb") as a, \
        open(os.path.join(GAME, "Balls_Data", "il2cpp_data", "Metadata", "global-metadata.dat"), "rb") as b:
    gen.load_il2cpp(a.read(), b.read())
nodes_json = gen.get_nodes_as_json("Unity.TextMeshPro", "TMPro.TMP_FontAsset")
nd = TypeTreeNode.from_list([TypeTreeNode(n["m_Level"], n["m_Type"], n["m_Name"], 0, 0, m_MetaFlag=n["m_MetaFlag"])
                             for n in json.loads(nodes_json)])
noto = next(o for o in af.objects.values()
            if o.type.name == "MonoBehaviour" and o.read(check_read=False).m_Name == "NotoSerif-Regular SDF")
tt = noto.read_typetree(nodes=nd)
PAD = tt["m_AtlasPadding"]

ft = TTFont(TTF)
cmap = ft.getBestCmap()
k = PT / ft["head"].unitsPerEm
pil = ImageFont.truetype(TTF, PT)
wanted = set(map(ord, EXTRA)) | set(range(0x20, 0x7F)) | set(range(0x400, 0x460))
wanted |= {c["m_Unicode"] for c in tt["m_CharacterTable"]}

# растеризуем глифы без сглаживания
glyphs = []  # (unicode, маска или None, метрики)
for u in sorted(wanted):
    if u < 0x20:  # \n, \r и т.п. из таблицы Noto: пустой глиф
        glyphs.append((u, None, dict(w=0, h=0, bx=0, by=0, adv=0)))
        continue
    if u not in cmap:
        continue
    ch = chr(u)
    adv = pil.getlength(ch)
    im = Image.new("L", (int(adv) + PT * 2, PT * 3))
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    d.text((PT // 2, PT * 2), ch, font=pil, fill=255, anchor="ls")
    bb = im.getbbox()
    if not bb or ch.isspace():
        glyphs.append((u, None, dict(w=0, h=0, bx=0, by=0, adv=round(adv))))
        continue
    glyphs.append((u, np.asarray(im.crop(bb)) > 127,
                   dict(w=bb[2] - bb[0], h=bb[3] - bb[1], bx=bb[0] - PT // 2, by=PT * 2 - bb[1], adv=round(adv))))

# раскладка по полкам
W, x, y, row, place = 1024, 0, 0, 0, {}
for u, mask, m in sorted((g for g in glyphs if g[1] is not None), key=lambda g: -g[2]["h"]):
    w, h = m["w"] + 2 * PAD, m["h"] + 2 * PAD
    if x + w > W:
        x, y, row = 0, y + row + 1, 0
    place[u] = (x, y)
    x, row = x + w + 1, max(row, h)
H = 1024
while H < y + row:
    H *= 2

atlas = np.zeros((H, W), np.float32)
table, chars, used = [], [], []
for i, (u, mask, m) in enumerate(glyphs, start=1):
    rect = dict(m_X=0, m_Y=0, m_Width=0, m_Height=0)
    if mask is not None:
        px, py = place[u]
        p = np.pad(mask, PAD)
        dist = np.where(p, edt(p) - 0.5, 0.5 - edt(~p))
        atlas[py:py + p.shape[0], px:px + p.shape[1]] = np.clip(0.5 + dist / (2 * SPREAD), 0, 1)
        rect = dict(m_X=px + PAD, m_Y=H - py - PAD - m["h"], m_Width=m["w"], m_Height=m["h"])
        used.append(dict(m_X=px, m_Y=H - py - p.shape[0], m_Width=p.shape[1], m_Height=p.shape[0]))
    table.append(dict(m_Index=i, m_Metrics=dict(m_Width=float(m["w"]), m_Height=float(m["h"]),
                                                m_HorizontalBearingX=float(m["bx"]), m_HorizontalBearingY=float(m["by"]),
                                                m_HorizontalAdvance=float(m["adv"])),
                      m_GlyphRect=rect, m_Scale=1.0, m_AtlasIndex=0, m_ClassDefinitionType=0))
    chars.append(dict(m_ElementType=1, m_Unicode=u, m_GlyphIndex=i, m_Scale=1.0))

hh, os2, post = ft["hhea"], ft["OS/2"], ft["post"]
fi = tt["m_FaceInfo"]
line = fi["m_LineHeight"] * fi["m_Scale"]  # межстрочный интервал оставляем как у Noto
fi.update(m_FamilyName=ft["name"].getDebugName(1), m_StyleName="Regular", m_PointSize=float(PT), m_Scale=SCALE,
          m_UnitsPerEM=ft["head"].unitsPerEm, m_LineHeight=line / SCALE, m_AscentLine=hh.ascent * k,
          m_CapLine=os2.sCapHeight * k, m_MeanLine=os2.sxHeight * k, m_Baseline=0.0, m_DescentLine=hh.descent * k,
          m_SuperscriptOffset=hh.ascent * k, m_SubscriptOffset=hh.descent * k,
          m_UnderlineOffset=post.underlinePosition * k, m_UnderlineThickness=max(post.underlineThickness * k, 100 * k),
          m_StrikethroughOffset=os2.sxHeight * k / 2, m_StrikethroughThickness=max(os2.yStrikeoutSize * k, 100 * k),
          m_TabWidth=float(round(pil.getlength(" "))))

os.makedirs(OUT, exist_ok=True)
a8 = Image.fromarray((atlas * 255 + 0.5).astype(np.uint8))
Image.merge("RGBA", [Image.new("L", a8.size, 255)] * 3 + [a8]).save(os.path.join(OUT, "atlas.png"))
with open(os.path.join(OUT, "font_data.json"), "w", encoding="utf8") as f:
    json.dump(dict(m_FaceInfo=fi, m_GlyphTable=table, m_CharacterTable=chars, m_UsedGlyphRects=used,
                   m_AtlasWidth=W, m_AtlasHeight=H, m_AtlasPadding=PAD,
                   characterSequence="".join(chr(c["m_Unicode"]) for c in chars)), f, ensure_ascii=False)
with open(os.path.join(OUT, "fontasset_nodes.json"), "w", encoding="utf8") as f:
    f.write(nodes_json)
missing = sorted(u for u in wanted if u not in cmap and u > 0x20)
print(f"{len(chars)} символов, атлас {W}x{H}" + (", нет в шрифте: " + "".join(map(chr, missing)) if missing else ""))
