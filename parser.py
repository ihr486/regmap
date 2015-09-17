#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function
import re
import sys
import os
from operator import attrgetter

re_address = re.compile(r"^@([A-Fa-f0-9]+)$")
re_option = re.compile(r"^#([a-z]+)\s+(\w+)$")
re_register = re.compile(r"^(([A-Za-z]\w*)/)?([A-Za-z]\w*)([.]([BHWR]+))?$")
re_field = re.compile(r"\s+([A-Za-z]\w*)([.]([AR]+))?(\s+\[(\d+)(:(\d+))?\])?$")
re_overlap = re.compile(r"^&$")

union_base = {1: "uint8_t BYTE", 2: "uint16_t WORD", 4: "uint32_t DWORD"}
type_names = {1: "uint8_t", 2: "uint16_t", 4: "uint32_t"}

class Field:
    def __init__(self, name, attr, start, end):
        self.name = name
        self.attr = attr
        self.start = start
        self.end = end

class Register:
    def __init__(self, name, attr, address):
        self.name = name
        self.attr = attr
        self.address = address
        self.layer_list = [[]]

        self.size = 1
        if attr.find("B") >= 0:
            self.size = 1
        if attr.find("H") >= 0:
            self.size = 2
        if attr.find("W") >= 0:
            self.size = 4

        self.atom = self.size
        if attr.find("W") >= 0:
            self.atom = 4
        if attr.find("H") >= 0:
            self.atom = 2
        if attr.find("B") >= 0:
            self.atom = 1

        self.atom_list = [self.atom] * self.size

    def addField(self, field):
        field_list = self.layer_list[-1]

        field_list.append(field)

        if field.start % 8 == 0 and field.end % 8 == 7:
            subunit_size = (field.end - field.start + 1) / 8
            if (field.start / 8) % subunit_size == 0:
                if subunit_size == self.atom or (field.attr and field.attr.find("A") >= 0):
                    for i in range(field.start / 8, field.end / 8 + 1):
                        self.atom_list[i] = subunit_size

    def addLayer(self):
        self.layer_list.append([])

    def printCHeader(self, prefix, out):
        for layer in self.layer_list:
            if len(layer) == 0:
                continue

            print("{0}\tstruct {{".format(prefix), file = out)

            bit_position = 0

            for field in layer:
                if field.attr and field.attr.find("R") >= 0:
                    modifier = "const "
                else:
                    modifier = ""

                if field.start < 0:
                    print("{0}\t\t{1}{2} {3} : 1;".format(prefix, modifier, type_names[self.atom_list[bit_position / 8]], field.name), file = out)

                    bit_position += 1
                else:
                    if bit_position < field.start:
                        max_atom = max(self.atom_list[bit_position / 8 : (field.start - 1) / 8 + 1])

                        print("{0}\t\t{1} : {2};".format(prefix, type_names[max_atom], field.start - bit_position), file = out)

                    if field.end < 0:
                        print("{0}\t\t{1}{2} {3} : 1;".format(prefix, modifier, type_names[self.atom_list[bit_position / 8]], field.name), file = out)

                        bit_position = field.start + 1
                    else:
                        max_atom = max(self.atom_list[field.start / 8 : field.end / 8 + 1])

                        print("{0}\t\t{1}{2} {3} : {4};".format(prefix, modifier, type_names[max_atom], field.name, field.end - field.start + 1), file = out)

                        bit_position = field.end + 1

            print("{0}\t}};".format(prefix), file = out)

class Module:
    def __init__(self, name):
        self.name = name
        self.register_list = []

    def addRegister(self, register):
        self.register_list.append(register)

    def printCHeader(self, out):
        if len(self.register_list) == 0:
            return

        if len(self.name) > 0:
            print("extern volatile struct {", file = out)
            prefix = "\t"
        else:
            prefix = ""

        self.register_list.sort(key = attrgetter("address"))

        address = self.register_list[0].address / 4 * 4
        spacer_count = 0

        for register in self.register_list:
            padding = register.address - address

            if len(self.name) > 0:
                if padding > 0:
                    print("\tuint8_t spacer{0:d}[{1:d}];".format(spacer_count, padding), file = out)

                if register.attr and register.attr.find("R") >= 0:
                    print("\tconst union {", file = out)
                else:
                    print("\tunion {", file = out)
            else:
                if register.attr and register.attr.find("R") >= 0:
                    print("extern const volatile union {", file = out)
                else:
                    print("extern volatile union {", file = out)

            print("{0}\t{1};".format(prefix, union_base[register.size]), file = out)

            register.printCHeader(prefix, out)

            print("{0}}} {1};".format(prefix, register.name), file = out)

            spacer_count += 1
            address = register.address + register.size

        if len(self.name) > 0:
            print("}} {0};".format(self.name), file = out)

    def printASMHeader(self, out):
        for register in self.register_list:
            if len(self.name) == 0:
                print("\t.set\t{0}, 0x{1:X}".format(register.name, register.address), file = out)
            else:
                print("\t.set\t{0}_{1}, 0x{2:X}".format(self.name, register.name, register.address), file = out)

    def printSymResolver(self, out):
        if len(self.register_list) == 0:
            return

        if len(self.name) == 0:
            for register in self.register_list:
                print("\t.global\t{0}".format(register.name), file = out)
                print("\t.set\t{0}, 0x{1:X}".format(register.name, register.address), file = out)
        else:
            self.register_list.sort(key = attrgetter("address"))

            base_address = self.register_list[0].address / 4 * 4

            print("\t.global\t{0}".format(self.name), file = out)
            print("\t.set\t{0}, 0x{1:X}".format(self.name, base_address), file = out)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please specify an input file.", file = sys.stderr)
        quit()

    address = 0
    radix = 10
    module_list = {}
    module = Module("")
    module_list[""] = module
    register = None

    regmap = open(sys.argv[1], "r")
    if not regmap:
        print("Failed to open {0}.".format(sys.argv[1]), file = sys.stderr)
        quit()

    for line in regmap:
        p = re_address.match(line)
        if p:
            new_address = int(p.group(1), radix)

            if new_address < address:
                print("Address reverting from {0:X} to {1:X}.".format(address, new_address), file = sys.stderr)

            address = new_address
            continue

        p = re_option.match(line)
        if p:
            if p.group(1) == "radix":
                radix = int(p.group(2), 10)

                print("Radix changed to {0:d}.".format(radix), file = sys.stderr)
            elif p.group(1) == "module":
                if not p.group(2) in module_list:
                    module = Module(p.group(2))
                    module_list[p.group(2)] = module
                else:
                    module = module_list[p.group(2)]

                print("Entered module {0}.".format(p.group(2)), file = sys.stderr)
            continue

        p = re_register.match(line)
        if p:
            if p.group(2):
                if p.group(2) in module_list:
                    module = module_list[p.group(2)]
                else:
                    module = Module(p.group(2))
                    module_list[p.group(2)] = module

            register = Register(p.group(3), p.group(5), address)
            module.addRegister(register)

            address += register.size
            continue

        p = re_field.match(line)
        if p:
            if p.group(5):
                start = int(p.group(5), 10)
            else:
                start = -1
            if p.group(7):
                end = start
                start = int(p.group(7), 10)
            else:
                end = start
            register.addField(Field(p.group(1), p.group(3), start, end))
            continue

        p = re_overlap.match(line)
        if p:
            register.addLayer()
            continue

        if len(line.strip()) > 0:
            print("Unrecognized line: \"{0}\".".format(line.strip()), file = sys.stderr)
            quit()

    regmap.close()

    (basename, ext) = os.path.splitext(sys.argv[1])

    c_header = open(basename + ".h", "w")
    if not c_header:
        print("Failed to open {0}.".format(basename + ".h"), file = sys.stderr)
        quit()

    asm_header = open(basename + ".inc", "w")
    if not asm_header:
        print("Failed to open {0}.".format(basename + ".inc"), file = sys.stderr)
        quit()

    sym_resolver = open(basename + ".S", "w")
    if not sym_resolver:
        print("Failed to open {0}.".format(basename + ".S"), file = sys.stderr)
        quit()

    for m in sorted(module_list.values(), key = attrgetter("name")):
        m.printCHeader(c_header)
        m.printASMHeader(asm_header)
        m.printSymResolver(sym_resolver)

    c_header.close()
    asm_header.close()
    sym_resolver.close()
