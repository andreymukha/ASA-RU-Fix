// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal C ABI for the independently built powzix/ooz decoder.
#include <stddef.h>
int Kraken_Decompress(const unsigned char *, size_t, unsigned char *, size_t);
extern "C" __declspec(dllexport) int asa_ooz_decompress(
    const unsigned char *source, size_t source_size,
    unsigned char *destination, size_t destination_size) {
    return Kraken_Decompress(source, source_size, destination, destination_size);
}
