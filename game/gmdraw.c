#include <Python.h>
#include <pygame/pygame.h>

PyObject* dbl_list (PyObject* self, PyObject* args) {
    PyObject *r, *tmp;
//     int i, n;
    if (!PyArg_ParseTuple(args, "O!", &PyRect_Type, &r)) return NULL;
    tmp = PyObject_CallMethod(r, "move_ip", "(ii)", 5, -10);
    Py_DECREF(tmp);
    Py_RETURN_NONE;
//     return r;
}

PyMethodDef methods[] = {
    {"dbl_list", dbl_list, METH_VARARGS},
    {NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC initstuff (void) {
    import_pygame_rect();
    (void) Py_InitModule("stuff", methods);
}
