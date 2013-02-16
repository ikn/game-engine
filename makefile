.PHONY: all clean distclean

all:
	CFLAGS="`pkg-config --cflags sdl`" ./setup
	cp -a build/lib*/*.so game/

clean:
	$(RM) -r build/ game/*.so

distclean: clean
	find -regex '.*\.py[co]' -delete
