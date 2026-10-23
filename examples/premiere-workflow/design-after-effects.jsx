/* Self-authored AE collaboration fixture. Run only with no unsaved current work. */
(function () {
    var root = File($.fileName).parent;
    var media = new Folder(root.fsName + "/media");
    var target = new File(media.fsName + "/motion.aep");
    if (target.exists) { throw new Error("Refusing to overwrite existing motion.aep"); }
    if (app.project && app.project.dirty) { throw new Error("Preserve unsaved AE work before running the fixture"); }
    app.newProject();
    var comp = app.project.items.addComp("Lizicut cards", 1280, 720, 1, 9.36, 25);
    function addCard(name, offset) {
        var footage = app.project.importFile(new ImportOptions(new File(media.fsName + "/" + name + ".png")));
        var layer = comp.layers.add(footage);
        layer.name = name;
        var position = layer.property("ADBE Transform Group").property("ADBE Position");
        position.setValueAtTime(0, [640 + offset, 360]);
        position.setValueAtTime(0.4, [640, 360]);
        var opacity = layer.property("ADBE Transform Group").property("ADBE Opacity");
        opacity.setValueAtTime(0, 0);
        opacity.setValueAtTime(0.24, 100);
        return layer;
    }
    addCard("revenue", -40);
    addCard("profit", 40);
    var line = comp.layers.addShape();
    line.name = "Comparison divider";
    var contents = line.property("ADBE Root Vectors Group");
    var group = contents.addProperty("ADBE Vector Group");
    var vectors = group.property("ADBE Vectors Group");
    var path = vectors.addProperty("ADBE Vector Shape - Group");
    var shape = new Shape();
    shape.vertices = [[0, -110], [0, 110]];
    shape.inTangents = [[0, 0], [0, 0]];
    shape.outTangents = [[0, 0], [0, 0]];
    shape.closed = false;
    path.property("ADBE Vector Shape").setValue(shape);
    var stroke = vectors.addProperty("ADBE Vector Graphic - Stroke");
    stroke.property("ADBE Vector Stroke Color").setValue([0.46, 0.50, 0.44]);
    stroke.property("ADBE Vector Stroke Width").setValue(2);
    var trim = vectors.addProperty("ADBE Vector Filter - Trim");
    trim.property("ADBE Vector Trim End").setValueAtTime(3.6, 0);
    trim.property("ADBE Vector Trim End").setValueAtTime(4.12, 100);
    app.project.save(target);
    var queue = app.project.renderQueue.items.add(comp);
    var module = queue.outputModule(1);
    return {project: target.fsName, composition: comp.name, layers: comp.numLayers, duration: comp.duration,
            outputTemplates: module.templates, renderTemplates: queue.templates};
}());
