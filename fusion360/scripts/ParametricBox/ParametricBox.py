# -*- coding: utf-8 -*-
"""
ParametricBox — 參數化收納盒 / 電子外殼（盒身 + 上蓋）

用途
  1. 驗證「Claude 寫腳本 → 你在 Fusion 360 執行」這條管線是否通。
  2. 之後所有需要外殼的產品都從這支腳本長出來。

執行方式（Fusion 360）
  Utilities 頁籤 → ADD-INS → Scripts and Add-Ins → Scripts → 綠色 + →
  選擇本資料夾 → 選 ParametricBox → Run

要改尺寸就改下面的 CFG，存檔後在 Fusion 裡再按一次 Run（會建到新文件裡）。
Fusion API 的內部長度單位是 cm，所以所有數值都經過 mm() 換算，不要直接傳 mm。
"""

import adsk.core
import adsk.fusion
import traceback

# ---------------------------------------------------------------- 參數
CFG = {
    # 內部可用空間（你要塞的東西的尺寸 + 餘裕）
    'inner_len':    120.0,   # 內長 X
    'inner_wid':     80.0,   # 內寬 Y
    'inner_hgt':     40.0,   # 內高 Z（從盒底內面算）

    # 壁厚 / 板厚 — 建議是噴頭直徑的整數倍（0.4 噴頭 → 2.0 / 2.4 / 2.8）
    'wall':           2.4,   # 側壁厚
    'floor_t':        2.0,   # 盒底厚
    'lid_t':          2.0,   # 蓋板厚

    # 蓋子（唇口式嵌合：蓋子的唇插進盒口內側）
    'lip_h':          4.0,   # 唇高
    'lip_wall':       1.6,   # 唇壁厚
    'fit_gap':        0.25,  # 單邊配合間隙，FDM 建議 0.2~0.3

    # 外觀
    'outer_fillet':   3.0,   # 四個直立角的外圓角（0 = 不倒角）

    # 排版：蓋子擺在盒子旁邊的間距，只影響畫面不影響零件
    'layout_gap':    15.0,
}

TOL = 1e-4  # 幾何比對容差（cm）


# ---------------------------------------------------------------- 小工具
def mm(v):
    """mm → Fusion 內部單位 cm"""
    return v / 10.0


def add_centered_rect(sketch, w, h):
    """在 sketch 原點畫一個置中矩形，w/h 已是內部單位"""
    p1 = adsk.core.Point3D.create(-w / 2.0, -h / 2.0, 0)
    p2 = adsk.core.Point3D.create(w / 2.0, h / 2.0, 0)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(p1, p2)


def pick_profile_by_area(sketch, target_area):
    """從 sketch 的多個 profile 中挑面積最接近 target_area 的那一個（用來取環形斷面）"""
    best, best_err = None, None
    for prof in sketch.profiles:
        err = abs(prof.areaProperties(
            adsk.fusion.CalculationAccuracy.LowCalculationAccuracy).area - target_area)
        if best_err is None or err < best_err:
            best, best_err = prof, err
    return best


def extrude(comp, profile, distance, operation, start_offset=None):
    """單向拉伸。distance 可為負。start_offset 為起始平面偏移量。"""
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(profile, operation)
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal(distance))
    if start_offset:
        inp.startExtent = adsk.fusion.OffsetStartDefinition.create(
            adsk.core.ValueInput.createByReal(start_offset))
    return ext.add(inp)


def fillet_outer_vertical_edges(comp, body, half_x, half_y, radius):
    """
    只對外輪廓那 4 條直立邊倒角。
    判定方式：邊是 Z 向直線，且中點同時落在 |x|=half_x 與 |y|=half_y 上
    → 這唯一對應外框的四個角，不會誤選內腔或唇口的邊。
    """
    if radius <= 0:
        return None

    edges = adsk.core.ObjectCollection.create()
    for edge in body.edges:
        geo = edge.geometry
        if geo.objectType != adsk.core.Line3D.classType():
            continue
        sp, ep = geo.startPoint, geo.endPoint
        if abs(sp.x - ep.x) > TOL or abs(sp.y - ep.y) > TOL:
            continue  # 不是直立邊
        if abs(abs(sp.x) - half_x) > TOL or abs(abs(sp.y) - half_y) > TOL:
            continue  # 不在外框角上
        edges.add(edge)

    if edges.count == 0:
        return None

    fillets = comp.features.filletFeatures
    inp = fillets.createInput()
    inp.addConstantRadiusEdgeSet(
        edges, adsk.core.ValueInput.createByReal(radius), True)
    return fillets.add(inp)


# ---------------------------------------------------------------- 盒身
def build_box(comp, d):
    # 1. 外形實體：底 + 側壁的整塊料
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = 'box_outer'
    add_centered_rect(sk, d['outer_len'], d['outer_wid'])
    body = extrude(comp, sk.profiles.item(0), d['floor_t'] + d['inner_hgt'],
                   adsk.fusion.FeatureOperations.NewBodyFeatureOperation
                   ).bodies.item(0)
    body.name = 'BoxShell'

    # 2. 挖內腔：從盒底內面往上切穿頂面（多切 1mm 確保穿透，切超出無副作用）
    sk2 = comp.sketches.add(comp.xYConstructionPlane)
    sk2.name = 'box_cavity'
    add_centered_rect(sk2, d['inner_len'], d['inner_wid'])
    extrude(comp, sk2.profiles.item(0), d['inner_hgt'] + mm(1.0),
            adsk.fusion.FeatureOperations.CutFeatureOperation,
            start_offset=d['floor_t'])

    # 3. 外角倒圓
    fillet_outer_vertical_edges(comp, body,
                                d['outer_len'] / 2.0, d['outer_wid'] / 2.0,
                                d['outer_fillet'])
    return body


# ---------------------------------------------------------------- 上蓋
def build_lid(comp, d):
    # 以「印出來時的姿態」建：蓋板貼平台，唇口朝上（不需支撐）
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = 'lid_plate'
    add_centered_rect(sk, d['outer_len'], d['outer_wid'])
    body = extrude(comp, sk.profiles.item(0), d['lid_t'],
                   adsk.fusion.FeatureOperations.NewBodyFeatureOperation
                   ).bodies.item(0)
    body.name = 'Lid'

    # 唇口：巢狀兩個矩形 → 取中間的環形斷面往上長
    lip_out_l = d['inner_len'] - 2 * d['fit_gap']
    lip_out_w = d['inner_wid'] - 2 * d['fit_gap']
    lip_in_l = lip_out_l - 2 * d['lip_wall']
    lip_in_w = lip_out_w - 2 * d['lip_wall']

    if lip_in_l <= 0 or lip_in_w <= 0:
        raise ValueError('lip_wall 太厚，唇口已無內孔，請調小 lip_wall')

    sk2 = comp.sketches.add(comp.xYConstructionPlane)
    sk2.name = 'lid_lip'
    add_centered_rect(sk2, lip_out_l, lip_out_w)
    add_centered_rect(sk2, lip_in_l, lip_in_w)
    ring_area = lip_out_l * lip_out_w - lip_in_l * lip_in_w
    extrude(comp, pick_profile_by_area(sk2, ring_area), d['lip_h'],
            adsk.fusion.FeatureOperations.JoinFeatureOperation,
            start_offset=d['lid_t'])

    fillet_outer_vertical_edges(comp, body,
                                d['outer_len'] / 2.0, d['outer_wid'] / 2.0,
                                d['outer_fillet'])
    return body


# ---------------------------------------------------------------- 主流程
def resolve(cfg):
    """把 mm 設定換算成內部單位，並補上衍生尺寸"""
    d = {k: mm(v) for k, v in cfg.items()}
    d['outer_len'] = d['inner_len'] + 2 * d['wall']
    d['outer_wid'] = d['inner_wid'] + 2 * d['wall']
    return d


def validate(cfg):
    problems = []
    if cfg['fit_gap'] < 0.15:
        problems.append('fit_gap < 0.15mm，FDM 幾乎一定會卡死，建議 0.2~0.3')
    if cfg['outer_fillet'] > 0 and cfg['outer_fillet'] >= cfg['wall'] + min(
            cfg['inner_len'], cfg['inner_wid']) / 2.0:
        problems.append('outer_fillet 過大，倒角會吃掉整面側壁')
    if cfg['lip_wall'] + cfg['fit_gap'] > cfg['wall']:
        problems.append(
            'lip_wall + fit_gap > wall：唇口比盒壁厚，蓋上後唇會凸出盒口內緣（結構仍可用，只是外觀不齊）')
    return problems


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
            design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('請先開啟一個 Fusion 設計文件再執行。')
            return

        warnings = validate(CFG)
        d = resolve(CFG)
        root = design.rootComponent

        # 盒身在原點
        box_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        box_occ.component.name = 'Box'
        build_box(box_occ.component, d)

        # 上蓋往 +Y 平移擺在旁邊
        shift = adsk.core.Matrix3D.create()
        shift.translation = adsk.core.Vector3D.create(
            0, d['outer_wid'] + d['layout_gap'], 0)
        lid_occ = root.occurrences.addNewComponent(shift)
        lid_occ.component.name = 'Lid'
        build_lid(lid_occ.component, d)

        msg = [
            'ParametricBox 建立完成',
            '',
            '外尺寸  : {:.1f} x {:.1f} x {:.1f} mm'.format(
                CFG['inner_len'] + 2 * CFG['wall'],
                CFG['inner_wid'] + 2 * CFG['wall'],
                CFG['floor_t'] + CFG['inner_hgt']),
            '內空間  : {:.1f} x {:.1f} x {:.1f} mm'.format(
                CFG['inner_len'], CFG['inner_wid'], CFG['inner_hgt']),
            '蓋合總高: {:.1f} mm'.format(
                CFG['floor_t'] + CFG['inner_hgt'] + CFG['lid_t']),
        ]
        if warnings:
            msg += ['', '提醒：'] + ['  - ' + w for w in warnings]
        ui.messageBox('\n'.join(msg))

    except Exception:
        if ui:
            ui.messageBox('ParametricBox 執行失敗:\n{}'.format(traceback.format_exc()))
