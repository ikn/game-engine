#include <Python.h>
#include <pygame/pygame.h>

PyObject* mk_disjoint (PyObject* add, PyObject* rm) {
    // both arguments are [pygame.Rect]
    PyObject* rs = PyList_New(0);
    return rs;
}

PyObject* fastdraw (PyObject* self, PyObject* args) {
    // don't do much error checking because the point of this is performance
    // and we own the class calling this; guaranteed to get
    // [obj], pygame.Surface, {obj: set(Graphic)}, [pygame.Rect]
    // and layers is sorted
    PyObject* layers_in, * sfc, * graphics_in, * dirty;
    if (!PyArg_UnpackTuple(args, "fastdraw", 4, 4, &layers_in, &sfc,
                           &graphics_in, &dirty))
        return NULL;

    PyObject** layers, *** graphics, ** gs, * g, * g_dirty, * g_rect, * r_o,
            ** graphics_obj, * tmp;
    PyObject* clip = PyString_FromString("clip"); // NOTE: ref[+1]
    int n_layers, * n_graphics;
    int i, j, k, n;
    // get arrays of layers, graphics and sizes
    // NOTE: ref[+2]
    layers_in = PySequence_Fast(layers_in, "layers: expected sequence");
    n_layers = PySequence_Fast_GET_SIZE(layers_in);
    layers = PySequence_Fast_ITEMS(layers_in);
    graphics_obj = PyMem_New(PyObject*, n_layers); // NOTE: alloc[+1]
    n_graphics = PyMem_New(int, n_layers); // NOTE: alloc[+2]
    graphics = PyMem_New(PyObject**, n_layers); // NOTE: alloc[+3]
    for (i = 0; i < n_layers; i++) {
        // NOTE: ref[+3]
        tmp = PySequence_Fast(PyDict_GetItem(graphics_in, layers[i]),
                              "graphics values: expected sequence");
        // need to keep it around since graphics references its array
        graphics_obj[i] = tmp;
        n_graphics[i] = PySequence_Fast_GET_SIZE(tmp);
        graphics[i] = PySequence_Fast_ITEMS(tmp);
    }
    // get dirty rects from graphics
    for (i = 0; i < n_layers; i++) {
        gs = graphics[i];
        for (j = 0; j < n_graphics[i]; j++) {
            g = gs[j];
            // NOTE: ref[+4] (list)
            g_dirty = PyObject_GetAttrString(g, "dirty");
            n = PyList_GET_SIZE(g_dirty);
            tmp = PyObject_GetAttrString(g, "was_visible"); // NOTE: ref[+5]
            if (tmp == Py_True) {
                // NOTE: ref[+6] (pygame.Rect)
                g_rect = PyObject_GetAttrString(g, "last_rect");
                for (k = 0; k < n; k++) {
                    r_o = PyList_GET_ITEM(g_dirty, k); // pygame.Rect
                    // NOTE: ref[+7]
                    r_o = PyObject_CallMethodObjArgs(r_o, clip, g_rect, NULL);
                    PyList_Append(dirty, r_o);
                    Py_DECREF(r_o); // NOTE: ref[-7]
                }
                Py_DECREF(g_rect); // NOTE: ref[-6]
            }
            Py_DECREF(tmp); // NOTE: ref[-5]
            tmp = PyObject_GetAttrString(g, "visible"); // NOTE: ref[+5]
            if (tmp == Py_True) {
                // NOTE: ref[+6] (pygame.Rect)
                g_rect = PyObject_GetAttrString(g, "rect");
                for (k = 0; k < n; k++) {
                    r_o = PyList_GET_ITEM(g_dirty, k); // pygame.Rect
                    // NOTE: ref[+7] (list)
                    r_o = PyObject_CallMethodObjArgs(r_o, clip, g_rect, NULL);
                    PyList_Append(dirty, r_o);
                    Py_DECREF(r_o); // NOTE: ref[-7]
                }
                Py_DECREF(g_rect); // NOTE: ref[-6]
            }
            Py_DECREF(tmp); // NOTE: ref[-5]
            Py_DECREF(g_dirty); // NOTE: ref[-4]
        }
    }
    // only have something to do if dirty is non-empty
    PyObject* rtn = Py_False;
    int n_dirty, r_new, r_good;
    n_dirty = PyList_GET_SIZE(dirty);
    if (PyList_GET_SIZE(dirty) == 0) {
        goto error;
    }

    PyObject* opaque_in = PyString_FromString("opaque_in"); // NOTE: ref[+4]
    PyObject* dirty_opaque = PyList_New(0); // NOTE: ref[+5]
    PyObject* l_dirty_opaque;
    PyRectObject* r, * tmp_r;
    // NOTE: alloc[+4]
    PyObject** dirty_by_layer = PyMem_New(PyObject*, n_layers);
    for (i = 0; i < n_layers; i++) {
        gs = graphics[i];
        // get opaque regions of dirty rects
        l_dirty_opaque = PyList_New(0); // NOTE: ref[+6]
        for (j = 0; j < n_dirty; j++) {
            r = (PyRectObject*) PyList_GET_ITEM(dirty, j); // pygame.Rect
            r_new = 0;
            r_good = 1;
            for (k = 0; k < n_graphics[i]; k++) {
                g = gs[k];
                g_rect = PyObject_GetAttrString(g, "rect"); // NOTE: ref[+7]
                if (r_new) tmp_r = r;
                // NOTE: ref[+8]
                r = (PyRectObject*)
                    PyObject_CallMethodObjArgs((PyObject*) r, clip, g_rect,
                                               NULL);
                if (r_new) Py_DECREF(tmp_r); // NOTE: ref[-8](k>0)
                r_new = 1;
                Py_DECREF(g_rect); // NOTE: ref[-7]
                // NOTE: ref[+7]
                tmp = PyObject_CallMethodObjArgs(g, opaque_in, (PyObject*) r,
                                                 NULL);
                r_good = r->r.w > 0 && r->r.h > 0 && tmp == Py_True;
                Py_DECREF(tmp); // NOTE: ref[-7]
                if (!r_good) break;
            }
            if (r_good) PyList_Append(l_dirty_opaque, (PyObject*) r);
            if (r_new) Py_DECREF((PyObject*) r); // NOTE: ref[-8](k=0)
        }
        // undirty below opaque graphics and make dirty rects disjoint
        // NOTE: ref[+7]
        dirty_by_layer[i] = mk_disjoint(dirty, dirty_opaque);
        tmp = dirty_opaque;
        // NOTE: ref[+8] (not sure why this returns a new reference)
        PySequence_InPlaceConcat(dirty_opaque, l_dirty_opaque);
        Py_DECREF(tmp); // NOTE: ref[-5] ref[-8+5]
        Py_DECREF(l_dirty_opaque); // NOTE: ref[-6] lef[-7+6]
    }

    // cleanup (in reverse order)
    // NOTE: ref[-6]
    for (i = 0; i < n_layers; i++) Py_DECREF(dirty_by_layer[i]);
    PyMem_Free(dirty_by_layer); // NOTE: alloc[-4]
    Py_DECREF(dirty_opaque); // NOTE: ref[-5]
    Py_DECREF(opaque_in); // NOTE: ref[-4]
error:
    for (i = 0; i < n_layers; i++) Py_DECREF(graphics_obj[i]); // NOTE: ref[-3]
    PyMem_Free(graphics); // NOTE: alloc[-3]
    PyMem_Free(n_graphics); // NOTE: alloc[-2]
    PyMem_Free(graphics_obj); // NOTE: alloc[-1]
    Py_DECREF(layers_in); // NOTE: ref[-2]
    Py_DECREF(clip); // NOTE: ref[-1]
    return rtn;
}

PyMethodDef methods[] = {
    {"fastdraw", fastdraw, METH_VARARGS, "Draw everything."},
    {NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC initgmdraw (void) {
    import_pygame_rect();
    Py_InitModule("gmdraw", methods);
}
