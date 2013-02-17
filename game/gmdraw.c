#include <Python.h>
#include <pygame/pygame.h>

PyObject* fastdraw (PyObject* self, PyObject* args) {
    // don't do much error checking because the point of this is performance
    // and we own the class calling this; guaranteed to get
    // [obj], pygame.Surface, {obj: set(Graphic)}, [pygame.Rect]
    // and layers is sorted
    PyObject* layers_in, * sfc, * graphics_in, * dirty;
    if (!PyArg_UnpackTuple(args, "fastdraw", 4, 4, &layers_in, &sfc,
                           &graphics_in, &dirty))
        return NULL;

    PyObject** layers, *** graphics, ** gs, * g, * g_dirty, * g_rect, * r,
            ** graphics_obj, * tmp;
    PyObject* clip = PyString_FromString("clip"); // NOTE: new ref
    int n_layers, * n_graphics;
    int i, j, k, n;
    // get arrays of layers, graphics and sizes
    // NOTE: new ref
    layers_in = PySequence_Fast(layers_in, "layers: expected sequence");
    n_layers = PySequence_Fast_GET_SIZE(layers_in);
    layers = PySequence_Fast_ITEMS(layers_in);
    graphics_obj = PyMem_New(PyObject*, n_layers); // NOTE: alloc
    n_graphics = PyMem_New(int, n_layers); // NOTE: alloc
    graphics = PyMem_New(PyObject**, n_layers); // NOTE: alloc
    for (i = 0; i < n_layers; i++) {
        // NOTE: new ref
        tmp = PySequence_Fast(PyDict_GetItem(graphics_in, layers[i]),
                              "graphics values: expected sequence");
        graphics_obj[i] = tmp;
        n_graphics[i] = PySequence_Fast_GET_SIZE(tmp);
        graphics[i] = PySequence_Fast_ITEMS(tmp);
    }
    // get dirty rects from graphics
    for (i = 0; i < n_layers; i++) {
        gs = graphics[i];
        for (j = 0; j < n_graphics[i]; j++) {
            g = gs[j];
            // NOTE: new ref (list)
            g_dirty = PyObject_GetAttrString(g, "dirty");
            n = PyList_GET_SIZE(g_dirty);
            tmp = PyObject_GetAttrString(g, "was_visible"); // NOTE: new ref
            if (tmp == Py_True) {
                // NOTE: new ref (pygame.Rect)
                g_rect = PyObject_GetAttrString(g, "last_rect");
                for (k = 0; k < n; k++) {
                    r = PyList_GET_ITEM(g_dirty, k); // pygame.Rect
                    // NOTE: new ref
                    r = PyObject_CallMethodObjArgs(r, clip, g_rect, NULL);
                    PyList_Append(dirty, r);
                    Py_DECREF(r);
                }
                Py_DECREF(g_rect);
            }
            Py_DECREF(tmp);
            tmp = PyObject_GetAttrString(g, "visible"); // NOTE: new ref
            if (tmp == Py_True) {
                // NOTE: new ref (pygame.Rect)
                g_rect = PyObject_GetAttrString(g, "rect");
                for (k = 0; k < n; k++) {
                    r = PyList_GET_ITEM(g_dirty, k); // pygame.Rect
                    // NOTE: new ref
                    r = PyObject_CallMethodObjArgs(r, clip, g_rect, NULL);
                    PyList_Append(dirty, r);
                    Py_DECREF(r);
                }
                Py_DECREF(g_rect);
            }
            Py_DECREF(tmp);
            Py_DECREF(g_dirty);
        }
    }
    // only have something to do if dirty is non-empty
    PyObject* rtn = Py_False;
    int n_dirty, r_new, r_good;
    n_dirty = PyList_GET_SIZE(dirty);
    if (PyList_GET_SIZE(dirty) == 0) {
        goto error;
    }

    PyObject* opaque_in = PyString_FromString("opaque_in"); // NOTE: new ref
    PyObject** dirty_opaque = PyMem_New(PyObject*, n_layers); // NOTE: alloc
    PyObject* l_dirty_opaque;
    PyObject* dirty_opaque_sum = PyList_New(0); // NOTE: new ref
    PyObject** dirty_by_layer = PyMem_New(PyObject*, n_layers); // NOTE: alloc
    for (i = 0; i < n_layers; i++) {
        gs = graphics[i];
        // get opaque regions of dirty rects
        l_dirty_opaque = PyList_New(0); // NOTE: new ref
        dirty_opaque[i] = l_dirty_opaque;
        for (j = 0; j < n_dirty; j++) {
            r = PyList_GET_ITEM(dirty, j); // pygame.Rect
            r_new = 0;
            r_good = 1;
            for (k = 0; k < n_graphics[i]; k++) {
                g = gs[k];
                g_rect = PyObject_GetAttrString(g, "rect"); // NOTE: new ref
                if (r_new) tmp = r;
                // NOTE: new ref
                r = PyObject_CallMethodObjArgs(r, clip, g_rect, NULL);
                if (r_new) Py_DECREF(tmp);
                r_new = 1;
                Py_DECREF(g_rect);
                // NOTE: new ref
                tmp = PyObject_CallMethodObjArgs(g, opaque_in, r, NULL);
                r_good = ((PyRectObject*) r)->r.w > 0 && \
                          ((PyRectObject*) r)->r.h > 0 && tmp == Py_True;
                Py_DECREF(tmp);
                if (!r_good) break;
            }
            if (r_good) PyList_Append(l_dirty_opaque, r);
            if (r_new) Py_DECREF(r);
        }
        // undirty below opaque graphics and make dirty rects disjoint
        // NOTE: new ref
        dirty_by_layer[i] = mk_disjoint(dirty, dirty_opaque_sum);
        tmp = dirty_opaque_sum;
        PySequence_InPlaceConcat(dirty_opaque_sum, l_dirty_opaque);
        // the above returns a new reference for some reason
        Py_DECREF(tmp);
    }

    // cleanup (in reverse order)
    for (i = 0; i < n_layers; i++) Py_DECREF(dirty_opaque[i]);
    PyMem_Free(dirty_by_layer);
    Py_DECREF(dirty_opaque_sum);
    PyMem_Free(dirty_opaque);
    Py_DECREF(opaque_in);
error:
    for (i = 0; i < n_layers; i++) Py_DECREF(graphics_obj[i]);
    PyMem_Free(graphics);
    PyMem_Free(n_graphics);
    PyMem_Free(graphics_obj);
    Py_DECREF(layers_in);
    Py_DECREF(clip);
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
