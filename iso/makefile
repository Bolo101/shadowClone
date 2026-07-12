# Define variables
SCRIPT := ./forgeIso.sh
BUILD_DIR := $(PWD)/debian-live-build

.PHONY: all clean

# Default target: run the script
all:
	chmod +x $(SCRIPT)
	bash $(SCRIPT)

# Clean target: remove the debian-live-build directory
clean:
	rm -rf $(BUILD_DIR)
