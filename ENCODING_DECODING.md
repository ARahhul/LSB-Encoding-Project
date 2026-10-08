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
| 1 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:289](lsb_stego/core.py#L289) | `bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))` | Encode: turns the secret bytes into a stream of bits. |
| 2 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:299](lsb_stego/core.py#L299) | `values \|= groups[:, j] << np.uint8(depth - 1 - j)` | Encode (2-bit mode): packs two secret bits into one value per channel. |
| 3 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:302](lsb_stego/core.py#L302) | `samples[start:end] = (samples[start:end] & keep) \| values` | **Encode: the LSB write.** Clears the low bits of each R/G/B value and ORs the secret bits in. |
| 4 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:359](lsb_stego/core.py#L359) | `_write(samples, 0, _header(flags, blob, depth), 1)` | Encode: writes the 13-byte header at 1 bit per channel. |
| 5 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:360](lsb_stego/core.py#L360) | `_write(samples, _HEADER_SAMPLES, blob, depth)` | Encode: writes the payload (blob) at the chosen depth, right after the header. |
| 6 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:369](lsb_stego/core.py#L369) | `Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)` | Encode: saves the result as a lossless PNG. |
| 7 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:313](lsb_stego/core.py#L313) | `bits = chunk & 1` | **Decode: the LSB read.** Takes the lowest bit of each R/G/B value. |
| 8 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:317](lsb_stego/core.py#L317) | `bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1` | Decode (2-bit mode): takes the two lowest bits of each value. |
| 9 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:319](lsb_stego/core.py#L319) | `return np.packbits(bits).tobytes()` | Decode: packs the bits back into bytes. |
| 10 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:432](lsb_stego/core.py#L432) | `magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))` | Decode: reads and unpacks the header (magic, flags, length, CRC). |
| 11 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:434](lsb_stego/core.py#L434) | `depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1` | Decode: gets the bit depth (1 or 2) from the header flags. |
| 12 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:437](lsb_stego/core.py#L437) | `blob = _read(carrier, _HEADER_SAMPLES, length, depth)` | Decode: reads the payload at that depth. |
| 13 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _open_blob()` | [lsb_stego/core.py:399](lsb_stego/core.py#L399) | `if zlib.crc32(blob) != crc:` | Decode: integrity check. A mismatch means the image was edited. |
| 14 | `crypto.py` | `LSB-Encoding-Project › lsb_stego › crypto.py › encrypt()` | [lsb_stego/crypto.py:36](lsb_stego/crypto.py#L36) | `ciphertext = AESGCM(derive_key(password, salt)).encrypt(nonce, plaintext, aad)` | Encode: AES-256-GCM encryption with a scrypt-derived key. |
| 15 | `crypto.py` | `LSB-Encoding-Project › lsb_stego › crypto.py › decrypt()` | [lsb_stego/crypto.py:45](lsb_stego/crypto.py#L45) | `return AESGCM(derive_key(password, salt)).decrypt(nonce, ciphertext, aad)` | Decode: AES-256-GCM decryption; a bad tag means a wrong password. |
| 16 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _decode_legacy()` | [lsb_stego/core.py:553](lsb_stego/core.py#L553) | `raw = np.packbits(red[:usable] & 1).tobytes()` | Decode (old format): reads red-channel LSBs written by the original encode.py. |
| 17 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:352](lsb_stego/core.py#L352) | `bpcs.embed(arr, _bpcs_header(flags, blob) + blob)` | **Encode (BPCS):** hides header + blob in the noisy bit-plane blocks. |
| 18 | `bpcs.py` | `LSB-Encoding-Project › lsb_stego › bpcs.py › embed()` | [lsb_stego/bpcs.py:138](lsb_stego/bpcs.py#L138) | `blocks[take] = payload[done:done + take.size]` | **Encode (BPCS): the block write.** Replaces noisy 8×8 blocks with secret blocks. |
| 19 | `bpcs.py` | `LSB-Encoding-Project › lsb_stego › bpcs.py › _data_blocks()` | [lsb_stego/bpcs.py:121](lsb_stego/bpcs.py#L121) | `blocks[simple] ^= CHECKERBOARD` | Encode (BPCS): conjugates secret blocks that are too simple to pass as noise. |
| 20 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:446](lsb_stego/core.py#L446) | `blob = bpcs.extract(arr, HEADER.size + length)[HEADER.size:]` | Decode (BPCS): reads the blob back from the noisy blocks. |
| 21 | `bpcs.py` | `LSB-Encoding-Project › lsb_stego › bpcs.py › extract()` | [lsb_stego/bpcs.py:175](lsb_stego/bpcs.py#L175) | `blocks[flagged] ^= CHECKERBOARD` | **Decode (BPCS):** undoes the conjugation of flagged blocks. |

## Part 1: Encoding (hiding data in an image)

### 1. `encode()`: the main encoding function

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › encode()`
- **Lines:** [lsb_stego/core.py:324-370](lsb_stego/core.py#L324-L370)

The public entry point every caller uses. It opens the cover, builds the payload, then either picks 1-bit or 2-bit LSB mode and writes the bits into every pixel, or (with `method="bpcs"`) hands the header and payload to BPCS, and saves a PNG.

```python
324  def encode(cover: ImageSource, secret: Secret, out_path: str | os.PathLike,
325             password: str | None = None, *, max_depth: int = MAX_DEPTH,
326             method: str = "lsb") -> EncodeResult:
327      """Hide ``secret`` in ``cover`` and write a lossless PNG to ``out_path``.
328  
329      ``method`` is ``"lsb"`` (default) or ``"bpcs"``. LSB uses 1 bit per
330      channel when the secret fits and up to ``max_depth`` bits when it
331      doesn't. BPCS hides in the picture's noisy areas only; see :mod:`bpcs`.
332      Any extension other than ``.png`` is replaced, because lossy formats
333      such as JPEG would destroy the hidden bits.
334      """
335      if method not in METHODS:
336          raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
337      img = open_image(cover, for_encoding=True)
338      blob, flags = _blob(secret, password)
339      size = HEADER.size + len(blob)
340      arr = np.array(img, dtype=np.uint8)
341  
342      if method == "bpcs":
343          # BPCS only rewrites noisy blocks, so an earlier LSB header in a smooth
344          # area would survive and be read first. Break its magic before BPCS
345          # picks its blocks (so the change can't shift them).
346          samples = arr[..., :3].reshape(-1)
347          if samples.size >= _HEADER_SAMPLES and _read(samples, 0, len(MAGIC), 1) == MAGIC:
348              arr[0, 0, 0] ^= 1
349          room = bpcs.capacity(arr)
350          if size > room:
351              raise CapacityError(size, room)
352          bpcs.embed(arr, _bpcs_header(flags, blob) + blob)
353          depth = 1
354      else:
355          depth = depth_needed(size, *img.size, max_depth=max_depth)
356          if depth is None:
357              raise CapacityError(size, capacity_for_size(*img.size, max_depth))
358          samples = arr[..., :3].reshape(-1)
359          _write(samples, 0, _header(flags, blob, depth), 1)
360          _write(samples, _HEADER_SAMPLES, blob, depth)
361          arr[..., :3] = samples.reshape(arr.shape[0], arr.shape[1], 3)
362          room = capacity_for_size(*img.size, depth)
363  
364      out = Path(out_path)
365      renamed = out.suffix.lower() != ".png"
366      if renamed:
367          out = out.with_suffix(".png")
368      out.parent.mkdir(parents=True, exist_ok=True)
369      Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)
370      return EncodeResult(out, size, room, renamed, depth, method)
```

**Key lines:**

- **337** `img = open_image(cover, for_encoding=True)`: opens and normalises the cover image
- **338** `blob, flags = _blob(secret, password)`: builds the payload: inner record → compress → encrypt
- **355** `depth = depth_needed(size, *img.size, max_depth=max_depth)`: picks the smallest bit depth that fits (1, else 2)
- **357** `raise CapacityError(size, capacity_for_size(*img.size, max_depth))`: raises `CapacityError` if it doesn't fit even at 2 bits
- **359** `_write(samples, 0, _header(flags, blob, depth), 1)`: header is always written at 1 bit per channel
- **360** `_write(samples, _HEADER_SAMPLES, blob, depth)`: payload written at the chosen depth
- **349** `room = bpcs.capacity(arr)`: BPCS: count the noisy blocks, which sets how much fits
- **352** `bpcs.embed(arr, _bpcs_header(flags, blob) + blob)`: BPCS: header and payload go into the noisy blocks (Part 5)
- **369** `Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)`: lossless PNG output (JPEG would destroy the bits)

### 2. `_write()`: the LSB embedding (core of encoding)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _write()`
- **Lines:** [lsb_stego/core.py:287-302](lsb_stego/core.py#L287-L302)

This is where the secret actually enters the pixels. Each R, G or B value keeps its upper bits, and its lowest 1 (or 2) bits are replaced with secret bits. NumPy does every pixel at once, so a 5 MB secret takes milliseconds.

```python
287  def _write(samples: np.ndarray, start: int, data: bytes, depth: int) -> None:
288      """Store ``data`` in the low ``depth`` bits of samples[start:], MSB first."""
289      bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
290      if depth == 1:
291          values = bits
292      else:
293          pad = (-bits.size) % depth
294          if pad:
295              bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
296          groups = bits.reshape(-1, depth)
297          values = np.zeros(groups.shape[0], dtype=np.uint8)
298          for j in range(depth):
299              values |= groups[:, j] << np.uint8(depth - 1 - j)
300      end = start + values.size
301      keep = np.uint8(0xFF ^ ((1 << depth) - 1))
302      samples[start:end] = (samples[start:end] & keep) | values
```

**Key lines:**

- **289** `bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))`: bytes → individual bits
- **299** `values |= groups[:, j] << np.uint8(depth - 1 - j)`: 2-bit mode: combine two bits per value
- **301** `keep = np.uint8(0xFF ^ ((1 << depth) - 1))`: mask that keeps the untouched upper bits (0xFE for 1-bit, 0xFC for 2-bit)
- **302** `samples[start:end] = (samples[start:end] & keep) | values`: **the write:** `(pixel & keep) | secret_bits`

### 3. `_blob()`: build the payload (compress + encrypt)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _blob()`
- **Lines:** [lsb_stego/core.py:230-236](lsb_stego/core.py#L230-L236)

Turns the secret into the bytes that get hidden, and sets the flags that tell the decoder what was done.

```python
230  def _blob(secret: Secret, password: str | None) -> tuple[bytes, int]:
231      blob, compressed = _compress(_inner_bytes(secret))
232      flags = FLAG_COMPRESSED if compressed else 0
233      if password:
234          blob = crypto.encrypt(blob, password, aad=MAGIC)
235          flags |= FLAG_ENCRYPTED
236      return blob, flags
```

### 4. `_inner_bytes()`: pack the text or file

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _inner_bytes()`
- **Lines:** [lsb_stego/core.py:208-216](lsb_stego/core.py#L208-L216)

Text is stored as UTF-8. Files keep their name, without folders, so the decoder can restore it.

```python
208  def _inner_bytes(secret: Secret) -> bytes:
209      if isinstance(secret, TextSecret):
210          kind, name, data = KIND_TEXT, b"", secret.text.encode("utf-8")
211      elif isinstance(secret, FileSecret):
212          base = Path(secret.name).name or "secret.bin"
213          kind, name, data = KIND_FILE, base[:MAX_NAME_CHARS].encode("utf-8"), secret.data
214      else:
215          raise TypeError(f"Unsupported secret type: {type(secret).__name__}")
216      return _INNER.pack(kind, len(name)) + name + data
```

### 5. `_compress()`: zlib, skipped for already-compressed data

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _compress()`
- **Lines:** [lsb_stego/core.py:219-227](lsb_stego/core.py#L219-L227)

Compresses text and documents. Photos, ZIPs and videos are detected from a 64 KB sample and stored as they are.

```python
219  def _compress(inner: bytes) -> tuple[bytes, bool]:
220      # Photos, archives and videos are already compressed: probe a sample so a
221      # multi-megabyte secret isn't run through zlib for nothing.
222      if len(inner) > 256 * 1024:
223          probe = inner[:64 * 1024]
224          if len(zlib.compress(probe, 1)) > len(probe) * 0.97:
225              return inner, False
226      packed = zlib.compress(inner, 6)
227      return (packed, True) if len(packed) < len(inner) else (inner, False)
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
- **Lines:** [lsb_stego/core.py:239-240](lsb_stego/core.py#L239-L240)

Writes `MAGIC | flags | length | CRC-32`. Bits 2–3 of the flags hold the bit depth.

```python
239  def _header(flags: int, blob: bytes, depth: int) -> bytes:
240      return HEADER.pack(MAGIC, flags | ((depth - 1) << DEPTH_SHIFT), len(blob), zlib.crc32(blob))
```

### 8. `capacity_for_size()` / `depth_needed()`: how much fits

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › capacity_for_size()`
- **Lines:** [lsb_stego/core.py:175-181](lsb_stego/core.py#L175-L181)

Capacity is `width × height × 3 × depth / 8` bytes. The encoder uses 1 bit when possible and 2 bits otherwise.

```python
175  def capacity_for_size(width: int, height: int, depth: int = MAX_DEPTH) -> int:
176      """Bytes (header included) that fit in an image of this size."""
177      samples = width * height * 3
178      header_samples = HEADER.size * 8
179      if samples < header_samples:
180          return samples // 8
181      return HEADER.size + (samples - header_samples) * depth // 8
```

### 9. `open_image()`: prepare the cover image

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › open_image()`
- **Lines:** [lsb_stego/core.py:152-172](lsb_stego/core.py#L152-L172)

Loads any Pillow-readable picture. It applies EXIF rotation and converts grayscale and palette images to RGB/RGBA, which crashed the original script.

```python
152  def open_image(source: ImageSource, *, for_encoding: bool = False) -> Image.Image:
153      """Open ``source`` and return it as an RGB or RGBA image."""
154      if isinstance(source, Image.Image):
155          img = source
156      else:
157          try:
158              img = Image.open(source)
159              img.load()
160          except FileNotFoundError:
161              raise
162          except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
163              raise UnsupportedImageError(f"This file can't be opened as an image ({exc}).") from exc
164      if for_encoding:
165          # Bake the EXIF rotation in so the output looks the way the user saw it.
166          img = ImageOps.exif_transpose(img)
167      if img.mode in ("RGB", "RGBA"):
168          return img
169      has_alpha = img.mode in ("LA", "PA", "La") or (img.mode == "P" and "transparency" in img.info)
170      if img.mode in ("I;16", "I;16B", "I;16L", "I"):
171          img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
172      return img.convert("RGBA" if has_alpha else "RGB")
```


## Part 2: Decoding (revealing hidden data)

### 10. `decode()`: the main decoding function

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › decode()`
- **Lines:** [lsb_stego/core.py:419-453](lsb_stego/core.py#L419-L453)

The public entry point every caller uses. It reads the LSB header; if there's none it looks for a BPCS header, and if there's neither it falls back to the original format. Passing `method="lsb"` or `method="bpcs"` limits the search to that method (the app passes the LSB/BPCS switch); leaving it out tries both. The checking, decrypting and decompressing shared by LSB and BPCS lives in `_open_blob()` (lines 396-416), which returns a `Revealed` (text or file).

```python
419  def decode(source: ImageSource, password: str | None = None, *,
420             method: str | None = None) -> Revealed:
421      """Extract whatever :func:`encode` (or the original ``encode.py``) hid.
422  
423      ``method`` limits the search to ``"lsb"`` (which includes the original
424      format) or ``"bpcs"``; by default both are tried and told apart by magic.
425      """
426      if method is not None and method not in METHODS:
427          raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
428      img = open_image(source)
429      carrier = _carrier(img)
430  
431      if method != "bpcs" and carrier.size >= _HEADER_SAMPLES:
432          magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))
433          if magic == MAGIC:
434              depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1
435              if length > capacity_for_size(*img.size, depth) - HEADER.size:
436                  raise CorruptDataError("The hidden content's length is larger than the image.")
437              blob = _read(carrier, _HEADER_SAMPLES, length, depth)
438              return _open_blob(flags, blob, crc, password, "lsb")
439  
440      found = _bpcs_header_of(img) if method != "lsb" else None
441      if found is not None:
442          arr, (_magic, flags, length, crc) = found
443          if length > carrier.size // 2:  # BPCS can never use more than half the bits
444              raise CorruptDataError("The hidden content's length is larger than the image.")
445          try:
446              blob = bpcs.extract(arr, HEADER.size + length)[HEADER.size:]
447          except ValueError as exc:
448              raise CorruptDataError("The hidden content runs past the end of the image.") from exc
449          return _open_blob(flags, blob, crc, password, "bpcs")
450  
451      if method == "bpcs":
452          raise NoHiddenDataError()
453      return _decode_legacy(img)
```

**Key lines:**

- **432** `magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))`: read the header at 1 bit per channel
- **433** `if magic == MAGIC:`: only trust it if the magic bytes `LSB\x02` are present
- **434** `depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1`: recover the bit depth from the flags
- **437** `blob = _read(carrier, _HEADER_SAMPLES, length, depth)`: read the payload at that depth
- **440** `found = _bpcs_header_of(img)`: no LSB header: look for the BPCS magic `BPC\x01` in the first noisy blocks
- **446** `blob = bpcs.extract(arr, HEADER.size + length)[HEADER.size:]`: BPCS: read the payload from the noisy blocks
- **399** `if zlib.crc32(blob) != crc:`: CRC-32 integrity check
- **409** `blob = crypto.decrypt(blob, password, aad=MAGIC)`: decrypt (raises `WrongPasswordError` on a bad password)
- **413** `blob = inflater.decompress(blob, MAX_DECOMPRESSED)`: decompress, with a 1 GB safety limit
- **416** `return _parse_inner(blob, encrypted=encrypted, compressed=compressed, method=method)`: unpack into text or file
- **453** `return _decode_legacy(img)`: no header: try the old format

### 11. `_read()`: the LSB extraction (core of decoding)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _read()`
- **Lines:** [lsb_stego/core.py:305-319](lsb_stego/core.py#L305-L319)

The exact inverse of `_write()`. It takes the lowest 1 (or 2) bits of each R, G and B value and packs them back into bytes.

```python
305  def _read(carrier: np.ndarray, start: int, count: int, depth: int) -> bytes:
306      """Inverse of :func:`_write`: ``count`` bytes from samples[start:]."""
307      nbits = count * 8
308      needed = -(-nbits // depth)
309      if start + needed > carrier.size:
310          raise CorruptDataError("The hidden content runs past the end of the image.")
311      chunk = carrier[start:start + needed]
312      if depth == 1:
313          bits = chunk & 1
314      else:
315          bits = np.empty((needed, depth), dtype=np.uint8)
316          for j in range(depth):
317              bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1
318          bits = bits.reshape(-1)[:nbits]
319      return np.packbits(bits).tobytes()
```

**Key lines:**

- **313** `bits = chunk & 1`: **the read (1-bit):** `value & 1`
- **317** `bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1`: **the read (2-bit):** shift and mask each bit
- **319** `return np.packbits(bits).tobytes()`: bits → bytes

### 12. `_carrier()`: flatten pixels into one channel stream

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _carrier()`
- **Lines:** [lsb_stego/core.py:281-284](lsb_stego/core.py#L281-L284)

Lays out every R, G and B value in reading order and skips alpha. Both `_read()` and `_write()` walk this order.

```python
281  def _carrier(img: Image.Image) -> np.ndarray:
282      """Flat uint8 array of every R, G and B sample (alpha excluded)."""
283      arr = np.asarray(img, dtype=np.uint8)
284      return arr[..., :3].reshape(-1)
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
- **Lines:** [lsb_stego/core.py:258-273](lsb_stego/core.py#L258-L273)

Reads the kind (text or file) and the file name, and returns the data as a `Revealed` object.

```python
258  def _parse_inner(inner: bytes, *, encrypted: bool, compressed: bool, method: str = "lsb") -> Revealed:
259      if len(inner) < _INNER.size:
260          raise CorruptDataError("The hidden content is truncated.")
261      kind, name_len = _INNER.unpack_from(inner)
262      start = _INNER.size + name_len
263      if kind not in (KIND_TEXT, KIND_FILE) or start > len(inner):
264          raise CorruptDataError("The hidden content is malformed.")
265      name = inner[_INNER.size:start].decode("utf-8", errors="replace") or None
266      return Revealed(
267          kind="text" if kind == KIND_TEXT else "file",
268          data=inner[start:],
269          name=name,
270          encrypted=encrypted,
271          compressed=compressed,
272          method=method,
273      )
```

### 15. `has_container()`: quick “does this image hide something?” check

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › has_container()`
- **Lines:** [lsb_stego/core.py:392-393](lsb_stego/core.py#L392-L393)

Reads only the 4 LSB magic bytes, or failing that the first two BPCS blocks. The GUI uses it to show *Contains hidden data* as soon as a picture is opened.

```python
392  def has_container(source: ImageSource) -> bool:
393      return detect_method(source) is not None
```

### 16. `_decode_legacy()`: images made by the original `encode.py`

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _decode_legacy()`
- **Lines:** [lsb_stego/core.py:544-567](lsb_stego/core.py#L544-L567)

The old format: red-channel LSBs, ending in four zero bytes, with no header or checksum. Results that are neither readable text nor a known file type are only offered as a candidate.

```python
544  def _decode_legacy(img: Image.Image) -> Revealed:
545      """Read the original format: red-channel LSBs ending in four NUL bytes.
546  
547      That format has no header, so any image "decodes" to something. Results
548      that are neither readable text nor a recognisable file type are reported
549      as :class:`NoHiddenDataError` with the raw bytes attached as a candidate.
550      """
551      red = np.asarray(img, dtype=np.uint8)[..., 0].reshape(-1)
552      usable = red.size - red.size % 8
553      raw = np.packbits(red[:usable] & 1).tobytes()
554      end = raw.find(LEGACY_TERMINATOR)
555      data = raw[:end] if end > 0 else b""
556      if not data:
557          raise NoHiddenDataError()
558  
559      text = _as_printable_text(data)
560      if text is not None:
561          return Revealed("text", text.encode("utf-8"), legacy=True)
562  
563      ext = _guess_extension(data)
564      candidate = Revealed("file", data, name=f"recovered{ext or '.bin'}", legacy=True)
565      if ext is None:
566          raise NoHiddenDataError(candidate=candidate)
567      return candidate
```

**Key lines:**

- **553** `raw = np.packbits(red[:usable] & 1).tobytes()`: read red-channel LSBs into bytes
- **554** `end = raw.find(LEGACY_TERMINATOR)`: find the four-zero-byte terminator


## Part 3: Where encoding and decoding are triggered

| Trigger | File | Breadcrumbs | Line | Code |
| --- | --- | --- | --- | --- |
| GUI **Hide Data…** button | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App.hide()` | [lsb_stego/gui/app.py:811](lsb_stego/gui/app.py#L811) | `self.worker.run(lambda: core.encode(cover.source, secret, path, password, method=method),` |
| GUI **Reveal** button / opening an image | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App.reveal()` | [lsb_stego/gui/app.py:902](lsb_stego/gui/app.py#L902) | `self.worker.run(lambda: core.decode(loaded.source, password, method=method), done, failed)` |
| GUI live *Space used* meter | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._compute_size()` | [lsb_stego/gui/app.py:708](lsb_stego/gui/app.py#L708) | `self.needed = core.container_size(secret, password)` |
| GUI LSB / BPCS switch (both tabs) | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._build()` | [lsb_stego/gui/app.py:252](lsb_stego/gui/app.py#L252) | `XPRadio(switch, "BPCS", self.method, "bpcs", command=self._on_method).pack(` |
| GUI **Show Where…** on Reveal | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App.show_data_map()` | [lsb_stego/gui/app.py:913](lsb_stego/gui/app.py#L913) | `return np.asarray(img, dtype=np.uint8), core.locate(img)` |
| GUI *Use BPCS / Use LSB* on Reveal | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._use_detected_method()` | [lsb_stego/gui/app.py:579](lsb_stego/gui/app.py#L579) | `self.method.set(self.inspected.data_method)` |
| GUI 1-bit / 2-bit indicator | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._refresh_hide()` | [lsb_stego/gui/app.py:727](lsb_stego/gui/app.py#L727) | `depth = core.depth_needed(need, self.cover.width, self.cover.height) \` |
| GUI *Contains hidden data* label | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › load_image()` | [lsb_stego/gui/app.py:156](lsb_stego/gui/app.py#L156) | `data_method = core.detect_method(img)` |
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
- **Lines:** [lsb_stego/bpcs.py:167-177](lsb_stego/bpcs.py#L167-L177)

Finds the same noisy blocks in the same order, undoes the conjugation of flagged blocks and joins their 63-bit payloads back into bytes.

```python
167  def extract(rgb: np.ndarray, count: int) -> bytes:
168      """The first ``count`` bytes hidden by :func:`embed`.
169  
170      Raises ValueError if the picture has fewer noisy blocks than that needs.
171      """
172      found = [blocks[take] for _p, _c, blocks, take in _holding(_gray_area(rgb), count)]
173      blocks = np.concatenate(found) if found else np.zeros((0, BLOCK, BLOCK), np.uint8)
174      flagged = blocks[:, 0, 0] == 1
175      blocks[flagged] ^= CHECKERBOARD
176      bits = blocks.reshape(-1, BLOCK * BLOCK)[:, 1:].reshape(-1)[:count * 8]
177      return np.packbits(bits).tobytes()
```

**Key lines:**

- **172** `found = [blocks[take] for _p, _c, blocks, take in _holding(_gray_area(rgb), count)]`: the noisy blocks holding the data, in embedding order
- **175** `blocks[flagged] ^= CHECKERBOARD`: undo conjugation where the flag bit is set
- **176** `bits = blocks.reshape(-1, BLOCK * BLOCK)[:, 1:].reshape(-1)[:count * 8]`: drop the flag bits, keep the data

## Part 6: Showing where the data is

### 22. `locate()`: map the hidden bits, pixel by pixel

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › locate()`
- **Lines:** [lsb_stego/core.py:456-497](lsb_stego/core.py#L456-L497)

Used by **Show Where…** on the Reveal tab. It finds the data the same way `decode()` does, but instead of reading it, it returns a `DataMap`: for every pixel and channel, a bit mask of which bits hold hidden data. No password is needed, because the header (magic, flags, length, CRC) isn't encrypted.

```python
456  def locate(source: ImageSource, *, method: str | None = None) -> DataMap:
457      """Map where :func:`decode` would find hidden data, bit by bit.
458  
459      No password is needed: the header that says where the data is isn't
460      encrypted. Raises :class:`NoHiddenDataError` if there is nothing to map.
461      """
462      if method is not None and method not in METHODS:
463          raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
464      img = open_image(source)
465      carrier = _carrier(img)
466      h, w = img.height, img.width
467  
468      if method != "bpcs" and carrier.size >= _HEADER_SAMPLES:
469          magic, flags, length, _crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))
470          if magic == MAGIC:
471              depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1
472              if length > capacity_for_size(w, h, depth) - HEADER.size:
473                  raise CorruptDataError("The hidden content's length is larger than the image.")
474              flat = np.zeros(carrier.size, dtype=np.uint8)
475              flat[:_HEADER_SAMPLES] = 1
476              end = _HEADER_SAMPLES + -(-length * 8 // depth)
477              flat[_HEADER_SAMPLES:end] = (1 << depth) - 1
478              return DataMap("lsb", flat.reshape(h, w, 3), HEADER.size + length, depth)
479  
480      found = _bpcs_header_of(img) if method != "lsb" else None
481      if found is not None:
482          arr, (_magic, _flags, length, _crc) = found
483          try:
484              bits, blocks = bpcs.bit_map(arr, HEADER.size + length)
485          except ValueError as exc:
486              raise CorruptDataError("The hidden content runs past the end of the image.") from exc
487          return DataMap("bpcs", bits, HEADER.size + length, blocks=blocks)
488  
489      if method == "bpcs":
490          raise NoHiddenDataError()
491      _decode_legacy(img)  # raises NoHiddenDataError unless the old format is plausible
492      red = np.asarray(img, dtype=np.uint8)[..., 0].reshape(-1)
493      usable = red.size - red.size % 8
494      stored = np.packbits(red[:usable] & 1).tobytes().find(LEGACY_TERMINATOR) + len(LEGACY_TERMINATOR)
495      bits = np.zeros((h * w, 3), dtype=np.uint8)
496      bits[:stored * 8, 0] = 1
497      return DataMap("legacy", bits.reshape(h, w, 3), stored)
```

**Key lines:**

- **475** `flat[:_HEADER_SAMPLES] = 1`: LSB: the 13-byte header is always in bit 0 of the first 104 values
- **477** `flat[_HEADER_SAMPLES:end] = (1 << depth) - 1`: LSB: then the payload, in the lowest 1 or 2 bits
- **484** `bits, blocks = bpcs.bit_map(arr, HEADER.size + length)`: BPCS: replay the noisy-block choice to find the blocks in use
- **496** `bits[:stored * 8, 0] = 1`: old format: red-channel LSBs up to the terminator

### 23. `bit_map()`: which 8×8 blocks hold BPCS data

- **File:** `bpcs.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › bpcs.py › bit_map()`
- **Lines:** [lsb_stego/bpcs.py:180-195](lsb_stego/bpcs.py#L180-L195)

Walks the noisy blocks in the same order as `embed()` and `extract()` (via `_holding()`), and marks each block's 64 pixels in its channel at its bit-plane.

```python
180  def bit_map(rgb: np.ndarray, count: int) -> tuple[np.ndarray, int]:
181      """Where the first ``count`` hidden bytes are, and how many blocks hold them.
182  
183      The map is (height, width, 3) uint8: bit ``k`` of ``map[y, x, c]`` is set
184      when bit-plane ``k`` of that channel's Gray-coded value carries data.
185      """
186      out = np.zeros((rgb.shape[0], rgb.shape[1], 3), dtype=np.uint8)
187      gray = _gray_area(rgb)
188      h, w = gray.shape[:2]
189      holding = _holding(gray, count)
190      for plane, channel, _blocks, take in holding:
191          used = np.zeros((h // BLOCK) * (w // BLOCK), dtype=bool)
192          used[take] = True
193          used = used.reshape(h // BLOCK, w // BLOCK).repeat(BLOCK, axis=0).repeat(BLOCK, axis=1)
194          out[:h, :w, channel] |= used.astype(np.uint8) << np.uint8(plane)
195      return out, sum(take.size for *_, take in holding)
```

**Key lines:**

- **189** `holding = _holding(gray, count)`: the same blocks `extract()` would read
- **194** `out[:h, :w, channel] |= used.astype(np.uint8) << np.uint8(plane)`: mark bit `plane` of that channel for every pixel in those blocks
