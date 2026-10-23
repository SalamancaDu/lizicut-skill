/* Self-authored technical example. Run in Photoshop; never closes user documents. */
(function () {
    var root = File($.fileName).parent;
    var media = new Folder(root.fsName + "/media");
    if (!media.exists) { throw new Error("Prepare the fixture media folder first"); }
    var target = new File(media.fsName + "/design.psd");
    if (target.exists) { throw new Error("Refusing to overwrite existing design.psd"); }
    var oldUnits = app.preferences.rulerUnits;
    var oldDialogs = app.displayDialogs;
    var doc;
    function color(hex) {
        var result = new SolidColor();
        result.rgb.hexValue = hex;
        return result;
    }
    function text(group, name, contents, x, y, size, hex) {
        var layer = group.artLayers.add();
        layer.kind = LayerKind.TEXT;
        layer.name = name;
        layer.textItem.contents = contents;
        layer.textItem.position = [UnitValue(x, "px"), UnitValue(y, "px")];
        layer.textItem.size = UnitValue(size, "pt");
        layer.textItem.font = "MicrosoftYaHei";
        layer.textItem.color = color(hex);
        return layer;
    }
    function rectangle(group, name, x, y, w, h, hex, opacity) {
        var layer = group.artLayers.add();
        layer.name = name;
        doc.activeLayer = layer;
        doc.selection.select([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]);
        doc.selection.fill(color(hex));
        doc.selection.deselect();
        layer.opacity = opacity;
        return layer;
    }
    function png(name) {
        var options = new PNGSaveOptions();
        options.compression = 9;
        options.interlaced = false;
        doc.saveAs(new File(media.fsName + "/" + name + ".png"), options, true, Extension.LOWERCASE);
    }
    try {
        app.preferences.rulerUnits = Units.PIXELS;
        app.displayDialogs = DialogModes.NO;
        doc = app.documents.add(1280, 720, 72, "Lizicut PR workflow design", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
        var title = doc.layerSets.add(); title.name = "Title and disclosure";
        text(title, "Disclosure", "虚构演示数据 · 不对应真实公司", 80, 75, 22, "A9B0A6");
        text(title, "Title", "营收增长，利润却下降", 80, 151, 48, "F4F1E8");
        var revenue = doc.layerSets.add(); revenue.name = "Revenue card";
        rectangle(revenue, "Card", 80, 220, 520, 300, "30362F", 100);
        text(revenue, "Label", "营收", 118, 287, 32, "D6DBD0");
        text(revenue, "Value", "+20%", 118, 422, 100, "6CCBB7");
        text(revenue, "Period", "100万 → 120万", 118, 482, 28, "D6DBD0");
        var profit = doc.layerSets.add(); profit.name = "Profit card";
        rectangle(profit, "Card", 680, 220, 520, 300, "30362F", 100);
        text(profit, "Label", "利润", 718, 287, 32, "D6DBD0");
        text(profit, "Value", "−40%", 718, 422, 100, "F2947F");
        text(profit, "Period", "20万 → 12万", 718, 482, 28, "D6DBD0");
        var caption1 = doc.layerSets.add(); caption1.name = "Caption 01";
        rectangle(caption1, "Subtitle backing", 80, 598, 1120, 94, "141713", 92);
        text(caption1, "Editable caption", "营收增长了，利润却下降了。", 170, 659, 36, "FFFFFF");
        var caption2 = doc.layerSets.add(); caption2.name = "Caption 02";
        rectangle(caption2, "Subtitle backing", 80, 598, 1120, 94, "141713", 92);
        text(caption2, "Editable caption", "看懂这个反差，先把几个数字放在同一张板上。", 120, 656, 32, "FFFFFF");
        caption1.visible = false; caption2.visible = false;
        var groups = [title, revenue, profit, caption1, caption2];
        png("design-preview");
        var names = ["title", "revenue", "profit", "caption-01", "caption-02"];
        for (var i = 0; i < groups.length; i++) {
            for (var j = 0; j < groups.length; j++) { groups[j].visible = (j === i); }
            png(names[i]);
        }
        title.visible = true; revenue.visible = true; profit.visible = true;
        caption1.visible = false; caption2.visible = false;
        var psd = new PhotoshopSaveOptions(); psd.layers = true;
        doc.saveAs(target, psd, false, Extension.LOWERCASE);
        return {documentId: doc.id, source: target.fsName, width: doc.width.as("px"), height: doc.height.as("px"), groups: groups.length, exported: names};
    } finally {
        app.preferences.rulerUnits = oldUnits;
        app.displayDialogs = oldDialogs;
    }
}());
