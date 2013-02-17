#include <Python.h>
#include <pygame/pygame.h>

#define MAX_LEVELS 300

void quicksort(int *arr, int elements) {
    // http://alienryderflex.com/quicksort/
    int piv, beg[MAX_LEVELS], end[MAX_LEVELS], i = 0, L, R, swap;
    beg[0] = 0;
    end[0] = elements;
    while (i >= 0) {
        L = beg[i];
        R = end[i] - 1;
        if (L < R) {
            piv = arr[L];
            while (L < R) {
                while (arr[R] >= piv && L < R) R--;
                if (L < R) arr[L++] = arr[R];
                while (arr[L] <= piv && L < R) L++;
                if (L < R) arr[R--] = arr[L];
            }
            arr[L] = piv;
            beg[i + 1] = L + 1;
            end[i + 1] = end[i];
            end[i++] = L;
            if (end[i] - beg[i] > end[i - 1] - beg[i - 1]) {
                swap = beg[i];
                beg[i] = beg[i - 1];
                beg[i - 1] = swap;
                swap = end[i];
                end[i] = end[i - 1];
                end[i - 1] = swap;
            }
        } else i--;
    }
}

int find (int *arr, int n, int x, int i) {
    for (; i < n; i++) {
        if (arr[i] == x) return i;
    }
    return -1;
}

int set_add (int *arr, int n, int x) {
    int i;
    for (i = 0; i < n; i++) {
        if (arr[i] == x) return 0;
    }
    arr[n] = x;
    return 1;
}

PyObject* mk_disjoint (PyObject* add, PyObject* rm) {
//     int s;
//     printf("add: ");
//     for (s = 0; s < PyList_GET_SIZE(add); s++) {
//         printf("(%d, %d, %d, %d) ", ((PyRectObject*) PyList_GET_ITEM(add, s))->r.x, ((PyRectObject*) PyList_GET_ITEM(add, s))->r.y, ((PyRectObject*) PyList_GET_ITEM(add, s))->r.w, ((PyRectObject*) PyList_GET_ITEM(add, s))->r.h);
//     }
//     printf("\n");
//     printf("rm: ");
//     for (s = 0; s < PyList_GET_SIZE(rm); s++) {
//         printf("(%d, %d, %d, %d) ", ((PyRectObject*) PyList_GET_ITEM(rm, s))->r.x, ((PyRectObject*) PyList_GET_ITEM(rm, s))->r.y, ((PyRectObject*) PyList_GET_ITEM(rm, s))->r.w, ((PyRectObject*) PyList_GET_ITEM(rm, s))->r.h);
//     }
//     printf("\n");
    // both arguments are [pygame.Rect]
    // turn into arrays
    add = PySequence_Fast(add, "expected list"); // NOTE: ref[+1]
    rm = PySequence_Fast(rm, "expected list"); // NOTE: ref[+2]
    int n_rects[2] = {PySequence_Fast_GET_SIZE(add),
                      PySequence_Fast_GET_SIZE(rm)};
    PyRectObject** rects[2] = {(PyRectObject**) PySequence_Fast_ITEMS(add),
                               (PyRectObject**) PySequence_Fast_ITEMS(rm)};
    // get edges
    int n_edges[2] = {0, 0}, i, j, k;
    GAME_Rect r;
    i = 2 * (n_rects[0] + n_rects[1]); // max number of edges
    int* edges[2] = {PyMem_New(int, i), PyMem_New(int, i)}; // NOTE: alloc[+1]
    for (i = 0; i < 2; i++) { // rects
        for (j = 0; j < n_rects[i]; j++) { // add|rm
            r = rects[i][j]->r;
            n_edges[0] += set_add(edges[0], n_edges[0], r.x);
            n_edges[0] += set_add(edges[0], n_edges[0], r.x + r.w);
            n_edges[1] += set_add(edges[1], n_edges[1], r.y);
            n_edges[1] += set_add(edges[1], n_edges[1], r.y + r.h);
        }
    }
    // sort edges
    quicksort(edges[0], n_edges[0]);
    quicksort(edges[1], n_edges[1]);
    // generate grid of (rows of) subrects and mark contents
    // each has 2 if add, has no 1 if rm
    i = (n_edges[0] - 1) * (n_edges[1] - 1);
    int* grid = PyMem_New(int, i);
    for (j = 0; j < i; j++) grid[j] = 1;
    int row0, row1, col0, col1, l;
    for (i = 0; i < 2; i++) { // rects
        for (j = 0; j < n_rects[i]; j++) { // add|rm
            r = rects[i][j]->r;
            if (r.w > 0 && r.h > 0) {
                row0 = find(edges[1], n_edges[1], r.y, 0);
                row1 = find(edges[1], n_edges[1], r.y + r.h, row0);
                col0 = find(edges[0], n_edges[0], r.x, 0);
                col1 = find(edges[0], n_edges[0], r.x + r.w, col0);
                for (k = row0; k < row1; k++) { // rows
                    for (l = col0; l < col1; l++) { // cols
                        if (i == 0) // add
                            grid[(n_edges[1] - 1) * k + l] |= 2;
                        else // rm (i == 1)
                            grid[(n_edges[1] - 1) * k + l] ^= 1;
                    }
                }
            }
        }
    }
    PyObject* r_o;
    // generate subrects
    PyObject* rs = PyList_New(0);
    for (i = 0; i < n_edges[1] - 1; i++) { // rows
        for (j = 0; j < n_edges[0] - 1; j++) { // cols
            if (grid[(n_edges[1] - 1) * i + j] == 3) { // add and not rm
                k = edges[0][j];
                l = edges[1][i];
                // NOTE: ref[+3]
                r_o = PyRect_New4(k, l, edges[0][j + 1] - k,
                                  edges[1][i + 1] - l);
                PyList_Append(rs, r_o);
                Py_DECREF(r_o); // NOTE: ref[-3]
            }
        }
    }
    // cleanup
    PyMem_Free(edges[0]);
    PyMem_Free(edges[1]); // NOTE: alloc[-1]
    Py_DECREF(rm); // NOTE: ref[-2]
    Py_DECREF(add); // NOTE: ref[-1]
//     printf("rtn: ");
//     for (i = 0; i < PyList_GET_SIZE(rs); i++) {
//         printf("(%d, %d, %d, %d) ", ((PyRectObject*) PyList_GET_ITEM(rs, i))->r.x, ((PyRectObject*) PyList_GET_ITEM(rs, i))->r.y, ((PyRectObject*) PyList_GET_ITEM(rs, i))->r.w, ((PyRectObject*) PyList_GET_ITEM(rs, i))->r.h);
//     }
//     printf("\n");
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
    char* dbl[4] = {"was_visible", "visible", "last_rect", "_rect"};
    PyObject* clip = PyString_FromString("clip"); // NOTE: ref[+1]
    int n_layers, * n_graphics;
    int i, j, k, l, n;
    // get arrays of layers, graphics and sizes
    // NOTE: ref[+2]
    layers_in = PySequence_Fast(layers_in, "layers: expected sequence");
    n_layers = PySequence_Fast_GET_SIZE(layers_in);
    layers = PySequence_Fast_ITEMS(layers_in);
    graphics_obj = PyMem_New(PyObject*, n_layers); // NOTE: alloc[+1]
    n_graphics = PyMem_New(int, n_layers); // NOTE: alloc[+2]
    graphics = PyMem_New(PyObject**, n_layers); // NOTE: alloc[+3]
    for (i = 0; i < n_layers; i++) { // graphics_in
        // NOTE: ref[+3]
        tmp = PySequence_Fast(PyDict_GetItem(graphics_in, layers[i]),
                              "graphics values: expected sequence");
        // need to keep it around since graphics references its array
        graphics_obj[i] = tmp;
        n_graphics[i] = PySequence_Fast_GET_SIZE(tmp);
        graphics[i] = PySequence_Fast_ITEMS(tmp);
    }
    // get dirty rects from graphics
    for (i = 0; i < n_layers; i++) { // graphics
        gs = graphics[i];
        for (j = 0; j < n_graphics[i]; j++) { // gs
            g = gs[j];
            // NOTE: ref[+4] (list)
            g_dirty = PyObject_GetAttrString(g, "dirty");
            n = PyList_GET_SIZE(g_dirty);
            for (k = 0; k < 2; k++) { // last/current
                tmp = PyObject_GetAttrString(g, dbl[k]); // NOTE: ref[+5]
                if (tmp == Py_True) {
                    // NOTE: ref[+6] (pygame.Rect)
                    g_rect = PyObject_GetAttrString(g, dbl[k + 2]);
                    for (l = 0; l < n; l++) { // g_dirty
                        r_o = PyList_GET_ITEM(g_dirty, l); // pygame.Rect
                        // NOTE: ref[+7]
                        r_o = PyObject_CallMethodObjArgs(r_o, clip, g_rect,
                                                         NULL);
                        PyList_Append(dirty, r_o);
                        Py_DECREF(r_o); // NOTE: ref[-7]
                    }
                    Py_DECREF(g_rect); // NOTE: ref[-6]
                }
                Py_DECREF(tmp); // NOTE: ref[-5]
            }
            Py_DECREF(g_dirty); // NOTE: ref[-4]
            tmp = PyObject_GetAttrString(g, "visible"); // NOTE: ref[+4]
            PyObject_SetAttrString(g, "was_visible", tmp);
            Py_DECREF(tmp); // NOTE: ref[-4]
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
    for (i = 0; i < n_layers; i++) { // graphics
        gs = graphics[i];
        n = n_graphics[i];
        // get opaque regions of dirty rects
        l_dirty_opaque = PyList_New(0); // NOTE: ref[+6]
        for (j = 0; j < n_dirty; j++) { // dirty
            r = (PyRectObject*) PyList_GET_ITEM(dirty, j); // pygame.Rect
            r_new = 0;
            r_good = 1;
            for (k = 0; k < n; k++) { // gs
                g = gs[k];
                g_rect = PyObject_GetAttrString(g, "_rect"); // NOTE: ref[+7]
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
        dirty_opaque = PySequence_InPlaceConcat(dirty_opaque, l_dirty_opaque);
        Py_DECREF(tmp); // NOTE: ref[-5] ref[-8+5]
        Py_DECREF(l_dirty_opaque); // NOTE: ref[-6] ref[-7+6]
    }

    PyObject* rs, * draw_in;
    PyObject* draw = PyString_FromString("draw"); // NOTE: ref[+7]
    // redraw in dirty rects
    for (i = n_layers - 1; i >= 0; i--) { // layers
        rs = dirty_by_layer[i];
        n = PyList_GET_SIZE(rs);
        gs = graphics[i];
        for (j = 0; j < n_graphics[i]; j++) { // gs
            g = gs[j];
            g_rect = PyObject_GetAttrString(g, "_rect"); // NOTE: ref[+8]
            draw_in = PyList_New(0); // NOTE: ref[+9]
            for (k = 0; k < n; k++) { // rs
                r = (PyRectObject*) PyList_GET_ITEM(rs, k);
                // NOTE: ref[+10]
                r = (PyRectObject*)
                    PyObject_CallMethodObjArgs(g_rect, clip, r, NULL);
                if (r->r.w > 0 && r->r.h > 0)
                    PyList_Append(draw_in, (PyObject*) r);
                Py_DECREF(r); // NOTE: ref[-10]
            }
            if (PyList_GET_SIZE(draw_in) > 0) {
                PyObject_CallMethodObjArgs(g, draw, sfc, draw_in, NULL);
            }
            tmp = PyList_New(0); // NOTE: ref[+10]
            PyObject_SetAttrString(g, "dirty", tmp);
            Py_DECREF(tmp); // NOTE: ref[-10]
            Py_DECREF(draw_in); // NOTE: ref[-9]
            Py_DECREF(g_rect); // NOTE: ref[-8]
        }
    }

    // add up dirty rects to return
    rtn = PyList_New(0); // new ref, but we're returning it
    for (i = 0; i < n_layers; i++) { // dirty_by_layer
        tmp = rtn;
        // NOTE: ref[+8] (not sure why this returns a new reference)
        rtn = PySequence_InPlaceConcat(rtn, dirty_by_layer[i]);
        Py_DECREF(tmp); // NOTE: ref[-8]
    }

    // cleanup (in reverse order)
    Py_DECREF(draw); // NOTE: ref[-7]
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
