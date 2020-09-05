PYTHON_VERSION := 2

.PHONY: all doc clean doc-clean distclean

all:
	echo $(PYTHON_VERSION) > py_ver
	CFLAGS="$(CFLAGS) `pkg-config --cflags sdl`" ./setup $(PYTHON_VERSION)
	@ # convert code if want Python 3
ifeq ($(PYTHON_VERSION), 3)
	./2to3
else
	./3to2
endif
	@ # Python 3 generates weirdly-named lib files
	cp -a build/lib*-$(PYTHON_VERSION).[0-9]*/*.so game/engine/gfx/_gm.so

doc:
	$(MAKE) -C doc/ html

clean: doc-clean
	./3to2
	$(RM) -r build/ py_ver bak/
	find -regex 'game/engine/.*\.so' -delete

doc-clean:
	$(MAKE) -C doc/ clean

distclean: clean doc-clean
	find -regex '.*\.py[co]' -delete
	find -regex '\(.*/\)?__pycache__' -delete
