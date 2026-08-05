# Headless EGL build of GDS3D. Separate from linux/Makefile so the interactive
# X11 binary is untouched: that one globs linux/*.cpp and owns its own main().
CC=g++
CFLAGS=-c -w -O1 -I ../math/ -I ../gdsoglviewer/ -I ../libgdsto3d/
LDFLAGS=-lEGL -lGL -static-libgcc -static-libstdc++ -fopenmp

SOURCES=$(wildcard *.cpp) $(wildcard ../math/*.cpp) $(wildcard ../gdsoglviewer/*.cpp) \
        $(wildcard ../libgdsto3d/*.cpp) $(wildcard ../libgdsto3d/clipper/*.cpp) \
        $(wildcard ../libgdsto3d/voro++/src/voro++.cc)
TMP_OBJECTS=$(SOURCES:.cc=.o)
OBJECTS=$(TMP_OBJECTS:.cpp=.o)
EXECUTABLE=./GDS3D_egl

all: $(EXECUTABLE)

$(EXECUTABLE): $(OBJECTS)
	$(CC) $(OBJECTS) -o $@ $(LDFLAGS)

.cpp.o:
	$(CC) $(CFLAGS) $< -o $@
.cc.o:
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm -f $(OBJECTS) $(EXECUTABLE)
.PHONY: all clean
