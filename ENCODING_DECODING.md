# Encoding & Decoding: Code Map

Where the encoding (hiding) and decoding (revealing) happens in this project, with file
names, breadcrumbs and the exact lines. All code below is copied straight from the source, so
the line numbers match the current files (version 2.0.0).

Two hiding methods share the same container (header + compressed/encrypted blob):
**LSB** (the default) writes into the lowest bits of every channel, and **BPCS** writes into
the picture's noisy 8×8 bit-plane blocks only (Part 5). Decoding detects which one was used.

**Breadcrumb format:** `Project › folder › file › function()`. Click a line link to open the file there.

## How it fits together

```
ENCODE (hide)                                           DECODE (reveal)
GUI  app.py › App.hide()        ─┐                 ┌─  GUI  app.py › App.reveal()
CLI  cli.py › _encode()          ─┤                 ├─  CLI  cli.py › _decode()
                                 ▼                 ▼
          core.py › encode()                      core.py › decode()
            ├─ open_image()      normalise to RGB/RGBA     ├─ open_image() + _carrier()
            ├─ _blob()                                     ├─ _read() header      (1 bit/channel)
            │   ├─ _inner_bytes()  text/file + name        ├─ depth from flags
            │   ├─ _compress()     zlib (skips JPG/ZIP)    ├─ _read() blob        (1 or 2 bits)
            │   └─ crypto.encrypt() AES-256-GCM            ├─ CRC-32 check
            ├─ method="lsb":                               │    (_open_blob: CRC, decrypt,
            │   ├─ depth_needed()  1-bit, else 2-bit       │     decompress, _parse_inner)
            │   ├─ _header()       magic|flags|len|CRC     ├─ crypto.decrypt()    (if password)
            │   └─ _write() header + blob     ◄─ LSB       ├─ zlib decompress     (if compressed)
            ├─ method="bpcs":                              ├─ _parse_inner() ─► Revealed
            │   ├─ bpcs.capacity()  noisy blocks only      ├─ else BPCS magic? bpcs.extract()
            │   └─ bpcs.embed()  header + blob ◄─ BPCS     │    ─► same CRC/decrypt/unpack
            └─ save PNG                                    └─ else _decode_legacy() (old format)
```

## The key lines at a glance

| # | File | Breadcrumbs | Line | Code | What it does |
| --- | --- | --- | --- | --- | --- |
| 1 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:259](lsb_stego/core.py#L259) | `bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))` | Encode: turns the secret bytes into a stream of bits. |
| 2 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:269](lsb_stego/core.py#L269) | `values \|= groups[:, j] << np.uint8(depth - 1 - j)` | Encode (2-bit mode): packs two secret bits into one value per channel. |
| 3 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:272](lsb_stego/core.py#L272) | `samples[start:end] = (samples[start:end] & keep) \| values` | **Encode: the LSB write.** Clears the low bits of each R/G/B value and ORs the secret bits in. |
| 4 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:329](lsb_stego/core.py#L329) | `_write(samples, 0, _header(flags, blob, depth), 1)` | Encode: writes the 13-byte header at 1 bit per channel. |
| 5 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:330](lsb_stego/core.py#L330) | `_write(samples, _HEADER_SAMPLES, blob, depth)` | Encode: writes the payload (blob) at the chosen depth, right after the header. |
| 6 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:339](lsb_stego/core.py#L339) | `Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)` | Encode: saves the result as a lossless PNG. |
| 7 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:283](lsb_stego/core.py#L283) | `bits = chunk & 1` | **Decode: the LSB read.** Takes the lowest bit of each R/G/B value. |
| 8 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:287](lsb_stego/core.py#L287) | `bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1` | Decode (2-bit mode): takes the two lowest bits of each value. |
| 9 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:289](lsb_stego/core.py#L289) | `return np.packbits(bits).tobytes()` | Decode: packs the bits back into bytes. |
| 10 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:402](lsb_stego/core.py#L402) | `magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))` | Decode: reads and unpacks the header (magic, flags, length, CRC). |
| 11 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:404](lsb_stego/core.py#L404) | `depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1` | Decode: gets the bit depth (1 or 2) from the header flags. |
| 12 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:407](lsb_stego/core.py#L407) | `blob = _read(carrier, _HEADER_SAMPLES, length, depth)` | Decode: reads the payload at that depth. |
| 13 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _open_blob()` | [lsb_stego/core.py:369](lsb_stego/core.py#L369) | `if zlib.crc32(blob) != crc:` | Decode: integrity check. A mismatch means the image was edited. |
| 14 | `crypto.py` | `LSB-Encoding-Project › lsb_stego › crypto.py › encrypt()` | [lsb_stego/crypto.py:36](lsb_stego/crypto.py#L36) | `ciphertext = AESGCM(derive_key(password, salt)).encrypt(nonce, plaintext, aad)` | Encode: AES-256-GCM encryption with a scrypt-derived key. |
| 15 | `crypto.py` | `LSB-Encoding-Project › lsb_stego › crypto.py › decrypt()` | [lsb_stego/crypto.py:45](lsb_stego/crypto.py#L45) | `return AESGCM(derive_key(password, salt)).decrypt(nonce, ciphertext, aad)` | Decode: AES-256-GCM decryption; a bad tag means a wrong password. |
| 16 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _decode_legacy()` | [lsb_stego/core.py:479](lsb_stego/core.py#L479) | `raw = np.packbits(red[:usable] & 1).tobytes()` | Decode (old format): reads red-channel LSBs written by the original encode.py. |
| 17 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:322](lsb_stego/core.py#L322) | `bpcs.embed(arr, _bpcs_header(flags, blob) + blob)` | **Encode (BPCS):** hides header + blob in the noisy bit-plane blocks. |
| 18 | `bpcs.py` | `LSB-Encoding-Project › lsb_stego › bpcs.py › embed()` | [lsb_stego/bpcs.py:138](lsb_stego/bpcs.py#L138) | `blocks[take] = payload[done:done + take.size]` | **Encode (BPCS): the block write.** Replaces noisy 8×8 blocks with secret blocks. |
| 19 | `bpcs.py` | `LSB-Encoding-Project › lsb_stego › bpcs.py › _data_blocks()` | [lsb_stego/bpcs.py:121](lsb_stego/bpcs.py#L121) | `blocks[simple] ^= CHECKERBOARD` | Encode (BPCS): conjugates secret blocks that are too simple to pass as noise. |
| 20 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:416](lsb_stego/core.py#L416) | `blob = bpcs.extract(arr, HEADER.size + length)[HEADER.size:]` | Decode (BPCS): reads the blob back from the noisy blocks. |
| 21 | `bpcs.py` | `LSB-Encoding-Project › lsb_stego › bpcs.py › extract()` | [lsb_stego/bpcs.py:169](lsb_stego/bpcs.py#L169) | `blocks[flagged] ^= CHECKERBOARD` | **Decode (BPCS):** undoes the conjugation of flagged blocks. |

## Part 1: Encoding (hiding data in an image)

### 1. `encode()`: the main encoding function

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › encode()`
- **Lines:** [lsb_stego/core.py:294-340](lsb_stego/core.py#L294-L340)

The public entry point every caller uses. It opens the cover, builds the payload, then either picks 1-bit or 2-bit LSB mode and writes the bits into every pixel, or (with `method="bpcs"`) hands the header and payload to BPCS, and saves a PNG.

```python
294  def encode(cover: ImageSource, secret: Secret, out_path: str | os.PathLike,
295             password: str | None = None, *, max_depth: int = MAX_DEPTH,
296             method: str = "lsb") -> EncodeResult:
297      """Hide ``secret`` in ``cover`` and write a lossless PNG to ``out_path``.
298  
299      ``method`` is ``"lsb"`` (default) or ``"bpcs"``. LSB uses 1 bit per
300      channel when the secret fits and up to ``max_depth`` bits when it
301      doesn't. BPCS hides in the picture's noisy areas only; see :mod:`bpcs`.
302      Any extension other than ``.png`` is replaced, because lossy formats
303      such as JPEG would destroy the hidden bits.
304      """
305      if method not in METHODS:
306          raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
307      img = open_image(cover, for_encoding=True)
308      blob, flags = _blob(secret, password)
309      size = HEADER.size + len(blob)
310      arr = np.array(img, dtype=np.uint8)
311  
312      if method == "bpcs":
313          # BPCS only rewrites noisy blocks, so an earlier LSB header in a smooth
314          # area would survive and be read first. Break its magic before BPCS
315          # picks its blocks (so the change can't shift them).
316          samples = arr[..., :3].reshape(-1)
317          if samples.size >= _HEADER_SAMPLES and _read(samples, 0, len(MAGIC), 1) == MAGIC:
318              arr[0, 0, 0] ^= 1
319          room = bpcs.capacity(arr)
320          if size > room:
321              raise CapacityError(size, room)
322          bpcs.embed(arr, _bpcs_header(flags, blob) + blob)
323          depth = 1
324      else:
325          depth = depth_needed(size, *img.size, max_depth=max_depth)
326          if depth is None:
327              raise CapacityError(size, capacity_for_size(*img.size, max_depth))
328          samples = arr[..., :3].reshape(-1)
329          _write(samples, 0, _header(flags, blob, depth), 1)
330          _write(samples, _HEADER_SAMPLES, blob, depth)
331          arr[..., :3] = samples.reshape(arr.shape[0], arr.shape[1], 3)
332          room = capacity_for_size(*img.size, depth)
333  
334      out = Path(out_path)
335      renamed = out.suffix.lower() != ".png"
336      if renamed:
337          out = out.with_suffix(".png")
338      out.parent.mkdir(parents=True, exist_ok=True)
339      Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)
340      return EncodeResult(out, size, room, renamed, depth, method)
```

**Key lines:**

- **307** `img = open_image(cover, for_encoding=True)`: opens and normalises the cover image
- **308** `blob, flags = _blob(secret, password)`: builds the payload: inner record → compress → encrypt
- **325** `depth = depth_needed(size, *img.size, max_depth=max_depth)`: picks the smallest bit depth that fits (1, else 2)
- **327** `raise CapacityError(size, capacity_for_size(*img.size, max_depth))`: raises `CapacityError` if it doesn't fit even at 2 bits
- **329** `_write(samples, 0, _header(flags, blob, depth), 1)`: header is always written at 1 bit per channel
- **330** `_write(samples, _HEADER_SAMPLES, blob, depth)`: payload written at the chosen depth
- **319** `room = bpcs.capacity(arr)`: BPCS: count the noisy blocks, which sets how much fits
- **322** `bpcs.embed(arr, _bpcs_header(flags, blob) + blob)`: BPCS: header and payload go into the noisy blocks (Part 5)
- **339** `Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)`: lossless PNG output (JPEG would destroy the bits)

### 2. `_write()`: the LSB embedding (core of encoding)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _write()`
- **Lines:** [lsb_stego/core.py:257-272](lsb_stego/core.py#L257-L272)

This is where the secret actually enters the pixels. Each R, G or B value keeps its upper bits, and its lowest 1 (or 2) bits are replaced with secret bits. NumPy does every pixel at once, so a 5 MB secret takes milliseconds.

```python
257  def _write(samples: np.ndarray, start: int, data: bytes, depth: int) -> None:
258      """Store ``data`` in the low ``depth`` bits of samples[start:], MSB first."""
259      bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
260      if depth == 1:
261          values = bits
262      else:
263          pad = (-bits.size) % depth
264          if pad:
265              bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
266          groups = bits.reshape(-1, depth)
267          values = np.zeros(groups.shape[0], dtype=np.uint8)
268          for j in range(depth):
269              values |= groups[:, j] << np.uint8(depth - 1 - j)
270      end = start + values.size
271      keep = np.uint8(0xFF ^ ((1 << depth) - 1))
272      samples[start:end] = (samples[start:end] & keep) | values
```

**Key lines:**

- **259** `bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))`: bytes → individual bits
- **269** `values |= groups[:, j] << np.uint8(depth - 1 - j)`: 2-bit mode: combine two bits per value
- **271** `keep = np.uint8(0xFF ^ ((1 << depth) - 1))`: mask that keeps the untouched upper bits (0xFE for 1-bit, 0xFC for 2-bit)
- **272** `samples[start:end] = (samples[start:end] & keep) | values`: **the write:** `(pixel & keep) | secret_bits`

### 3. `_blob()`: build the payload (compress + encrypt)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _blob()`
- **Lines:** [lsb_stego/core.py:200-206](lsb_stego/core.py#L200-L206)

Turns the secret into the bytes that get hidden, and sets the flags that tell the decoder what was done.

```python
200  def _blob(secret: Secret, password: str | None) -> tuple[bytes, int]:
201      blob, compressed = _compress(_inner_bytes(secret))
202      flags = FLAG_COMPRESSED if compressed else 0
203      if password:
204          blob = crypto.encrypt(blob, password, aad=MAGIC)
205          flags |= FLAG_ENCRYPTED
206      return blob, flags
```

### 4. `_inner_bytes()`: pack the text or file

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _inner_bytes()`
- **Lines:** [lsb_stego/core.py:178-186](lsb_stego/core.py#L178-L186)

Text is stored as UTF-8. Files keep their name, without folders, so the decoder can restore it.

```python
178  def _inner_bytes(secret: Secret) -> bytes:
179      if isinstance(secret, TextSecret):
180          kind, name, data = KIND_TEXT, b"", secret.text.encode("utf-8")
181      elif isinstance(secret, FileSecret):
182          base = Path(secret.name).name or "secret.bin"
183          kind, name, data = KIND_FILE, base[:MAX_NAME_CHARS].encode("utf-8"), secret.data
184      else:
185          raise TypeError(f"Unsupported secret type: {type(secret).__name__}")
186      return _INNER.pack(kind, len(name)) + name + data
```

### 5. `_compress()`: zlib, skipped for already-compressed data

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _compress()`
- **Lines:** [lsb_stego/core.py:189-197](lsb_stego/core.py#L189-L197)

Compresses text and documents. Photos, ZIPs and videos are detected from a 64 KB sample and stored as they are.

```python
189  def _compress(inner: bytes) -> tuple[bytes, bool]:
190      # Photos, archives and videos are already compressed: probe a sample so a
191      # multi-megabyte secret isn't run through zlib for nothing.
192      if len(inner) > 256 * 1024:
193          probe = inner[:64 * 1024]
194          if len(zlib.compress(probe, 1)) > len(probe) * 0.97:
195              return inner, False
196      packed = zlib.compress(inner, 6)
197      return (packed, True) if len(packed) < len(inner) else (inner, False)
```

### 6. `encrypt()` / `derive_key()`: password protection

- **File:** `crypto.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › crypto.py › encrypt()`
- **Lines:** [lsb_stego/crypto.py:32-37](lsb_stego/crypto.py#L32-L37)

scrypt turns the password into a 256-bit key, and AES-256-GCM encrypts the payload. The output is `salt | nonce | ciphertext+tag`.

```python
32  def encrypt(plaintext: bytes, password: str, aad: bytes = b"") -> bytes:
33      """Return ``salt | nonce | ciphertext+tag``."""
34      salt = os.urandom(SALT_LEN)
35      nonce = os.urandom(NONCE_LEN)
36      ciphertext = AESGCM(derive_key(password, salt)).encrypt(nonce, plaintext, aad)
37      return salt + nonce + ciphertext
```

### 7. `_header()`: the 13-byte header

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _header()`
- **Lines:** [lsb_stego/core.py:209-210](lsb_stego/core.py#L209-L210)

Writes `MAGIC | flags | length | CRC-32`. Bits 2–3 of the flags hold the bit depth.

```python
209  def _header(flags: int, blob: bytes, depth: int) -> bytes:
210      return HEADER.pack(MAGIC, flags | ((depth - 1) << DEPTH_SHIFT), len(blob), zlib.crc32(blob))
```

### 8. `capacity_for_size()` / `depth_needed()`: how much fits

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › capacity_for_size()`
- **Lines:** [lsb_stego/core.py:145-151](lsb_stego/core.py#L145-L151)

Capacity is `width × height × 3 × depth / 8` bytes. The encoder uses 1 bit when possible and 2 bits otherwise.

```python
145  def capacity_for_size(width: int, height: int, depth: int = MAX_DEPTH) -> int:
146      """Bytes (header included) that fit in an image of this size."""
147      samples = width * height * 3
148      header_samples = HEADER.size * 8
149      if samples < header_samples:
150          return samples // 8
151      return HEADER.size + (samples - header_samples) * depth // 8
```

### 9. `open_image()`: prepare the cover image

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › open_image()`
- **Lines:** [lsb_stego/core.py:122-142](lsb_stego/core.py#L122-L142)

Loads any Pillow-readable picture. It applies EXIF rotation and converts grayscale and palette images to RGB/RGBA, which crashed the original script.

```python
122  def open_image(source: ImageSource, *, for_encoding: bool = False) -> Image.Image:
123      """Open ``source`` and return it as an RGB or RGBA image."""
124      if isinstance(source, Image.Image):
125          img = source
126      else:
127          try:
128              img = Image.open(source)
129              img.load()
130          except FileNotFoundError:
131              raise
132          except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
133              raise UnsupportedImageError(f"This file can't be opened as an image ({exc}).") from exc
134      if for_encoding:
135          # Bake the EXIF rotation in so the output looks the way the user saw it.
136          img = ImageOps.exif_transpose(img)
137      if img.mode in ("RGB", "RGBA"):
138          return img
139      has_alpha = img.mode in ("LA", "PA", "La") or (img.mode == "P" and "transparency" in img.info)
140      if img.mode in ("I;16", "I;16B", "I;16L", "I"):
141          img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
142      return img.convert("RGBA" if has_alpha else "RGB")
```


## Part 2: Decoding (revealing hidden data)

### 10. `decode()`: the main decoding function

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › decode()`
- **Lines:** [lsb_stego/core.py:389-423](lsb_stego/core.py#L389-L423)

The public entry point every caller uses. It reads the LSB header; if there's none it looks for a BPCS header, and if there's neither it falls back to the original format. Passing `method="lsb"` or `method="bpcs"` limits the search to that method (the app passes the LSB/BPCS switch); leaving it out tries both. The checking, decrypting and decompressing shared by LSB and BPCS lives in `_open_blob()` (lines 366-386), which returns a `Revealed` (text or file).

```python
389  def decode(source: ImageSource, password: str | None = None, *,
390             method: str | None = None) -> Revealed:
391      """Extract whatever :func:`encode` (or the original ``encode.py``) hid.
392  
393      ``method`` limits the search to ``"lsb"`` (which includes the original
394      format) or ``"bpcs"``; by default both are tried and told apart by magic.
395      """
396      if method is not None and method not in METHODS:
397          raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
398      img = open_image(source)
399      carrier = _carrier(img)
400  
401      if method != "bpcs" and carrier.size >= _HEADER_SAMPLES:
402          magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))
403          if magic == MAGIC:
404              depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1
405              if length > capacity_for_size(*img.size, depth) - HEADER.size:
406                  raise CorruptDataError("The hidden content's length is larger than the image.")
407              blob = _read(carrier, _HEADER_SAMPLES, length, depth)
408              return _open_blob(flags, blob, crc, password, "lsb")
409  
410      found = _bpcs_header_of(img) if method != "lsb" else None
411      if found is not None:
412          arr, (_magic, flags, length, crc) = found
413          if length > carrier.size // 2:  # BPCS can never use more than half the bits
414              raise CorruptDataError("The hidden content's length is larger than the image.")
415          try:
416              blob = bpcs.extract(arr, HEADER.size + length)[HEADER.size:]
417          except ValueError as exc:
418              raise CorruptDataError("The hidden content runs past the end of the image.") from exc
419          return _open_blob(flags, blob, crc, password, "bpcs")
420  
421      if method == "bpcs":
422          raise NoHiddenDataError()
423      return _decode_legacy(img)
```

**Key lines:**

- **402** `magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))`: read the header at 1 bit per channel
- **403** `if magic == MAGIC:`: only trust it if the magic bytes `LSB\x02` are present
- **404** `depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1`: recover the bit depth from the flags
- **407** `blob = _read(carrier, _HEADER_SAMPLES, length, depth)`: read the payload at that depth
- **410** `found = _bpcs_header_of(img)`: no LSB header: look for the BPCS magic `BPC\x01` in the first noisy blocks
- **416** `blob = bpcs.extract(arr, HEADER.size + length)[HEADER.size:]`: BPCS: read the payload from the noisy blocks
- **369** `if zlib.crc32(blob) != crc:`: CRC-32 integrity check
- **379** `blob = crypto.decrypt(blob, password, aad=MAGIC)`: decrypt (raises `WrongPasswordError` on a bad password)
- **383** `blob = inflater.decompress(blob, MAX_DECOMPRESSED)`: decompress, with a 1 GB safety limit
- **386** `return _parse_inner(blob, encrypted=encrypted, compressed=compressed, method=method)`: unpack into text or file
- **423** `return _decode_legacy(img)`: no header: try the old format

### 11. `_read()`: the LSB extraction (core of decoding)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _read()`
- **Lines:** [lsb_stego/core.py:275-289](lsb_stego/core.py#L275-L289)

The exact inverse of `_write()`. It takes the lowest 1 (or 2) bits of each R, G and B value and packs them back into bytes.

```python
275  def _read(carrier: np.ndarray, start: int, count: int, depth: int) -> bytes:
276      """Inverse of :func:`_write`: ``count`` bytes from samples[start:]."""
277      nbits = count * 8
278      needed = -(-nbits // depth)
279      if start + needed > carrier.size:
280          raise CorruptDataError("The hidden content runs past the end of the image.")
281      chunk = carrier[start:start + needed]
282      if depth == 1:
283          bits = chunk & 1
284      else:
285          bits = np.empty((needed, depth), dtype=np.uint8)
286          for j in range(depth):
287              bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1
288          bits = bits.reshape(-1)[:nbits]
289      return np.packbits(bits).tobytes()
```

**Key lines:**

- **283** `bits = chunk & 1`: **the read (1-bit):** `value & 1`
- **287** `bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1`: **the read (2-bit):** shift and mask each bit
- **289** `return np.packbits(bits).tobytes()`: bits → bytes

### 12. `_carrier()`: flatten pixels into one channel stream

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _carrier()`
- **Lines:** [lsb_stego/core.py:251-254](lsb_stego/core.py#L251-L254)

Lays out every R, G and B value in reading order and skips alpha. Both `_read()` and `_write()` walk this order.

```python
251  def _carrier(img: Image.Image) -> np.ndarray:
252      """Flat uint8 array of every R, G and B sample (alpha excluded)."""
253      arr = np.asarray(img, dtype=np.uint8)
254      return arr[..., :3].reshape(-1)
```

### 13. `decrypt()`: unlock password-protected content

- **File:** `crypto.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › crypto.py › decrypt()`
- **Lines:** [lsb_stego/crypto.py:40-47](lsb_stego/crypto.py#L40-L47)

Splits `salt | nonce | ciphertext`, derives the key again and decrypts. AES-GCM's tag check detects a wrong password.

```python
40  def decrypt(blob: bytes, password: str, aad: bytes = b"") -> bytes:
41      if len(blob) < OVERHEAD:
42          raise CorruptDataError("The encrypted content is truncated.")
43      salt, nonce, ciphertext = blob[:SALT_LEN], blob[SALT_LEN:SALT_LEN + NONCE_LEN], blob[SALT_LEN + NONCE_LEN:]
44      try:
45          return AESGCM(derive_key(password, salt)).decrypt(nonce, ciphertext, aad)
46      except InvalidTag:
47          raise WrongPasswordError("The password is incorrect.") from None
```

### 14. `_parse_inner()`: rebuild the text or file

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _parse_inner()`
- **Lines:** [lsb_stego/core.py:228-243](lsb_stego/core.py#L228-L243)

Reads the kind (text or file) and the file name, and returns the data as a `Revealed` object.

```python
228  def _parse_inner(inner: bytes, *, encrypted: bool, compressed: bool, method: str = "lsb") -> Revealed:
229      if len(inner) < _INNER.size:
230          raise CorruptDataError("The hidden content is truncated.")
231      kind, name_len = _INNER.unpack_from(inner)
232      start = _INNER.size + name_len
233      if kind not in (KIND_TEXT, KIND_FILE) or start > len(inner):
234          raise CorruptDataError("The hidden content is malformed.")
235      name = inner[_INNER.size:start].decode("utf-8", errors="replace") or None
236      return Revealed(
237          kind="text" if kind == KIND_TEXT else "file",
238          data=inner[start:],
239          name=name,
240          encrypted=encrypted,
241          compressed=compressed,
242          method=method,
243      )
```

### 15. `has_container()`: quick “does this image hide something?” check

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › has_container()`
- **Lines:** [lsb_stego/core.py:362-363](lsb_stego/core.py#L362-L363)

Reads only the 4 LSB magic bytes, or failing that the first two BPCS blocks. The GUI uses it to show *Contains hidden data* as soon as a picture is opened.

```python
362  def has_container(source: ImageSource) -> bool:
363      return detect_method(source) is not None
```

### 16. `_decode_legacy()`: images made by the original `encode.py`

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _decode_legacy()`
- **Lines:** [lsb_stego/core.py:470-493](lsb_stego/core.py#L470-L493)

The old format: red-channel LSBs, ending in four zero bytes, with no header or checksum. Results that are neither readable text nor a known file type are only offered as a candidate.

```python
470  def _decode_legacy(img: Image.Image) -> Revealed:
471      """Read the original format: red-channel LSBs ending in four NUL bytes.
472  
473      That format has no header, so any image "decodes" to something. Results
474      that are neither readable text nor a recognisable file type are reported
475      as :class:`NoHiddenDataError` with the raw bytes attached as a candidate.
476      """
477      red = np.asarray(img, dtype=np.uint8)[..., 0].reshape(-1)
478      usable = red.size - red.size % 8
479      raw = np.packbits(red[:usable] & 1).tobytes()
480      end = raw.find(LEGACY_TERMINATOR)
481      data = raw[:end] if end > 0 else b""
482      if not data:
483          raise NoHiddenDataError()
484  
485      text = _as_printable_text(data)
486      if text is not None:
487          return Revealed("text", text.encode("utf-8"), legacy=True)
488  
489      ext = _guess_extension(data)
490      candidate = Revealed("file", data, name=f"recovered{ext or '.bin'}", legacy=True)
491      if ext is None:
492          raise NoHiddenDataError(candidate=candidate)
493      return candidate
```

**Key lines:**

- **479** `raw = np.packbits(red[:usable] & 1).tobytes()`: read red-channel LSBs into bytes
- **480** `end = raw.find(LEGACY_TERMINATOR)`: find the four-zero-byte terminator


## Part 3: Where encoding and decoding are triggered

| Trigger | File | Breadcrumbs | Line | Code |
| --- | --- | --- | --- | --- |
| GUI **Hide Data…** button | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App.hide()` | [lsb_stego/gui/app.py:806](lsb_stego/gui/app.py#L806) | `self.worker.run(lambda: core.encode(cover.source, secret, path, password, method=method),` |
| GUI **Reveal** button / opening an image | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App.reveal()` | [lsb_stego/gui/app.py:896](lsb_stego/gui/app.py#L896) | `self.worker.run(lambda: core.decode(loaded.source, password, method=method), done, failed)` |
| GUI live *Space used* meter | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._compute_size()` | [lsb_stego/gui/app.py:703](lsb_stego/gui/app.py#L703) | `self.needed = core.container_size(secret, password)` |
| GUI LSB / BPCS switch (both tabs) | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._build()` | [lsb_stego/gui/app.py:250](lsb_stego/gui/app.py#L250) | `XPRadio(switch, "BPCS", self.method, "bpcs", command=self._on_method).pack(` |
| GUI *Use BPCS / Use LSB* on Reveal | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._use_detected_method()` | [lsb_stego/gui/app.py:574](lsb_stego/gui/app.py#L574) | `self.method.set(self.inspected.data_method)` |
| GUI 1-bit / 2-bit indicator | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._refresh_hide()` | [lsb_stego/gui/app.py:722](lsb_stego/gui/app.py#L722) | `depth = core.depth_needed(need, self.cover.width, self.cover.height) \` |
| GUI *Contains hidden data* label | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › load_image()` | [lsb_stego/gui/app.py:155](lsb_stego/gui/app.py#L155) | `data_method = core.detect_method(img)` |
| CLI `lsb-encode` / `python encode.py` | `cli.py` | `LSB-Encoding-Project › lsb_stego › cli.py › _encode()` | [lsb_stego/cli.py:84](lsb_stego/cli.py#L84) | `result = core.encode(image_path, secret, output, password or None, method=method)` |
| CLI `lsb-decode` / `python decode.py` | `cli.py` | `LSB-Encoding-Project › lsb_stego › cli.py › _decode()` | [lsb_stego/cli.py:99](lsb_stego/cli.py#L99) | `revealed = core.decode(image_path)` |
| CLI password retry | `cli.py` | `LSB-Encoding-Project › lsb_stego › cli.py › _decode()` | [lsb_stego/cli.py:101](lsb_stego/cli.py#L101) | `revealed = core.decode(image_path, getpass.getpass("🔒 Enter the password: "))` |
| Script `encode.py` | `encode.py` | `LSB-Encoding-Project › encode.py` | [encode.py:6](encode.py#L6) | `raise SystemExit(encode_main())` |
| Script `decode.py` | `decode.py` | `LSB-Encoding-Project › decode.py` | [decode.py:6](decode.py#L6) | `raise SystemExit(decode_main())` |
| Poetry command `lsb-encode` | `pyproject.toml` | `LSB-Encoding-Project › pyproject.toml › [project.scripts]` | [pyproject.toml:15](pyproject.toml#L15) | `lsb-encode = "lsb_stego.cli:encode_main"` |
| Poetry command `lsb-decode` | `pyproject.toml` | `LSB-Encoding-Project › pyproject.toml › [project.scripts]` | [pyproject.toml:16](pyproject.toml#L16) | `lsb-decode = "lsb_stego.cli:decode_main"` |

## Part 4: Format constants

### 17. Container format definitions

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py`
- **Lines:** [lsb_stego/core.py:50-65](lsb_stego/core.py#L50-L65)

The magic bytes, the header layout (`>4sBII` = magic, flags, length, CRC), the flag bits, and the 2-bit maximum depth.

```python
50  MAGIC = b"LSB\x02"
51  MAGIC_BPCS = b"BPC\x01"
52  METHODS = ("lsb", "bpcs")
53  HEADER = struct.Struct(">4sBII")
54  _INNER = struct.Struct(">BH")
55  
56  FLAG_COMPRESSED = 0x01
57  FLAG_ENCRYPTED = 0x02
58  DEPTH_SHIFT = 2
59  DEPTH_MASK = 0x0C
60  MAX_DEPTH = 2          # used automatically when 1 bit per channel is not enough
61  KIND_TEXT = 0
62  KIND_FILE = 1
63  
64  MAX_NAME_CHARS = 255
65  PNG_LEVEL = 3          # as small as level 6 on LSB-noisy pixels, and faster
```

## Part 5: BPCS (Bit-Plane Complexity Segmentation)

BPCS is the second hiding method, chosen with the *Method: LSB / BPCS* switch at the top of
the app (it applies to Hide and Reveal), `B` in `lsb-encode`, or
`core.encode(..., method="bpcs")` / `core.decode(..., method="bpcs")`. LSB changes the lowest bit of every channel. BPCS
changes whole 8×8 blocks, and only in areas that already look like noise, so smooth areas
such as sky stay untouched while busy areas can carry data in their lowest **4** bit-planes.

1. Each R, G and B value is converted to **Gray code**, so each bit-plane behaves like an
   independent black-and-white picture.
2. Each bit-plane is cut into 8×8 blocks. A block's **complexity** is its number of
   black/white borders divided by the maximum of 112. Blocks at or above **α = 0.3**
   count as noise.
3. Noisy blocks are replaced, in order (plane 0 first, then R, G, B, then block row by row),
   by secret blocks: 63 data bits plus a flag bit in the top-left corner.
4. A secret block that is too simple is **conjugated** (XORed with a checkerboard), which turns
   complexity α into 1 − α and sets the flag, so the reader can undo it.

Every block that carries data is still complex afterwards and every other block is
unchanged, so the reader finds exactly the same blocks. How much fits depends on the
picture: a busy photo can hold more than LSB, and a flat graphic holds nothing.

### 18. `embed()`: the BPCS write (core of BPCS encoding)

- **File:** `bpcs.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › bpcs.py › embed()`
- **Lines:** [lsb_stego/bpcs.py:125-146](lsb_stego/bpcs.py#L125-L146)

Walks the noisy blocks in order and overwrites them with secret blocks, then converts the Gray-code planes back to ordinary pixel values.

```python
125  def embed(rgb: np.ndarray, data: bytes) -> int:
126      """Hide ``data`` in ``rgb`` in place. Returns the blocks used.
127  
128      Raises ValueError if the picture doesn't have enough noisy blocks.
129      """
130      payload = _data_blocks(data)
131      h, w = _crop(rgb)
132      gray = _gray_area(rgb)
133      done = 0
134      if gray.size:
135          for plane, channel, blocks, idx in _noisy(gray):
136              take = idx[:payload.shape[0] - done]
137              if take.size:
138                  blocks[take] = payload[done:done + take.size]
139                  _store_plane(gray, channel, plane, blocks)
140                  done += take.size
141              if done == payload.shape[0]:
142                  break
143      if done < payload.shape[0]:
144          raise ValueError("not enough complex areas in the picture")
145      rgb[:h, :w, :3] = _from_gray(gray)
146      return done
```

**Key lines:**

- **135** `for plane, channel, blocks, idx in _noisy(gray):`: noisy blocks, plane by plane, channel by channel
- **138** `blocks[take] = payload[done:done + take.size]`: **the write:** replace noisy blocks with secret blocks
- **139** `_store_plane(gray, channel, plane, blocks)`: put the changed bit-plane back
- **145** `rgb[:h, :w, :3] = _from_gray(gray)`: Gray code back to pixel values

### 19. `_data_blocks()`: secret bytes to 8×8 blocks, with conjugation

- **File:** `bpcs.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › bpcs.py › _data_blocks()`
- **Lines:** [lsb_stego/bpcs.py:111-122](lsb_stego/bpcs.py#L111-L122)

Packs 63 secret bits into each block, leaving the corner bit for the conjugation flag, and conjugates any block too simple to pass as noise.

```python
111  def _data_blocks(data: bytes) -> np.ndarray:
112      """``data`` as (n, 8, 8) blocks: flag bit + 63 data bits, conjugated if simple."""
113      bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
114      count = -(-bits.size // DATA_BITS)
115      padded = np.zeros(count * DATA_BITS, dtype=np.uint8)
116      padded[:bits.size] = bits
117      flat = np.zeros((count, BLOCK * BLOCK), dtype=np.uint8)
118      flat[:, 1:] = padded.reshape(count, DATA_BITS)
119      blocks = flat.reshape(count, BLOCK, BLOCK)
120      simple = complexity(blocks) < THRESHOLD
121      blocks[simple] ^= CHECKERBOARD
122      return blocks
```

**Key lines:**

- **118** `flat[:, 1:] = padded.reshape(count, DATA_BITS)`: 63 data bits per block; bit 0 is the flag
- **120** `simple = complexity(blocks) < THRESHOLD`: which secret blocks look too simple
- **121** `blocks[simple] ^= CHECKERBOARD`: conjugate them (also sets the flag bit)

### 20. `complexity()`: how "noisy" an 8×8 block is

- **File:** `bpcs.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › bpcs.py › complexity()`
- **Lines:** [lsb_stego/bpcs.py:62-66](lsb_stego/bpcs.py#L62-L66)

Counts the borders between neighbouring bits across and down. Blocks with at least `THRESHOLD` (34 of 112) borders carry data.

```python
62  def complexity(blocks: np.ndarray) -> np.ndarray:
63      """Border count of each (…, 8, 8) block of 0/1 bits (0 to 112)."""
64      across = (blocks[..., :, 1:] != blocks[..., :, :-1]).sum(axis=(-2, -1))
65      down = (blocks[..., 1:, :] != blocks[..., :-1, :]).sum(axis=(-2, -1))
66      return across + down
```

### 21. `extract()`: the BPCS read (core of BPCS decoding)

- **File:** `bpcs.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › bpcs.py › extract()`
- **Lines:** [lsb_stego/bpcs.py:149-171](lsb_stego/bpcs.py#L149-L171)

Finds the same noisy blocks in the same order, undoes the conjugation of flagged blocks and joins their 63-bit payloads back into bytes.

```python
149  def extract(rgb: np.ndarray, count: int) -> bytes:
150      """The first ``count`` bytes hidden by :func:`embed`.
151  
152      Raises ValueError if the picture has fewer noisy blocks than that needs.
153      """
154      needed = -(-count * 8 // DATA_BITS)
155      gray = _gray_area(rgb)
156      found: list[np.ndarray] = []
157      have = 0
158      if gray.size:
159          for _plane, _channel, blocks, idx in _noisy(gray):
160              take = idx[:needed - have]
161              found.append(blocks[take])
162              have += take.size
163              if have == needed:
164                  break
165      if have < needed:
166          raise ValueError("the picture ends before the hidden data does")
167      blocks = np.concatenate(found) if found else np.zeros((0, BLOCK, BLOCK), np.uint8)
168      flagged = blocks[:, 0, 0] == 1
169      blocks[flagged] ^= CHECKERBOARD
170      bits = blocks.reshape(-1, BLOCK * BLOCK)[:, 1:].reshape(-1)[:count * 8]
171      return np.packbits(bits).tobytes()
```

**Key lines:**

- **161** `found.append(blocks[take])`: collect noisy blocks until there are enough
- **169** `blocks[flagged] ^= CHECKERBOARD`: undo conjugation where the flag bit is set
- **170** `bits = blocks.reshape(-1, BLOCK * BLOCK)[:, 1:].reshape(-1)[:count * 8]`: drop the flag bits, keep the data
