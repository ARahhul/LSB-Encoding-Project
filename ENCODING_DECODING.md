# Encoding & Decoding: Code Map

Where the encoding (hiding) and decoding (revealing) happens in this project, with file
names, breadcrumbs and the exact lines. All code below is copied straight from the source, so
the line numbers match the current files (version 2.0.0).

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
            ├─ depth_needed()    1-bit, else 2-bit         ├─ crypto.decrypt()    (if password)
            ├─ _header()         magic|flags|len|CRC       ├─ zlib decompress     (if compressed)
            ├─ _write() header + _write() blob   ◄─ LSB    ├─ _parse_inner() ─► Revealed
            └─ save PNG                                    └─ else _decode_legacy() (old format)
```

## The key lines at a glance

| # | File | Breadcrumbs | Line | Code | What it does |
| --- | --- | --- | --- | --- | --- |
| 1 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:241](lsb_stego/core.py#L241) | `bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))` | Encode: turns the secret bytes into a stream of bits. |
| 2 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:251](lsb_stego/core.py#L251) | `values \|= groups[:, j] << np.uint8(depth - 1 - j)` | Encode (2-bit mode): packs two secret bits into one value per channel. |
| 3 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _write()` | [lsb_stego/core.py:254](lsb_stego/core.py#L254) | `samples[start:end] = (samples[start:end] & keep) \| values` | **Encode: the LSB write.** Clears the low bits of each R/G/B value and ORs the secret bits in. |
| 4 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:293](lsb_stego/core.py#L293) | `_write(samples, 0, _header(flags, blob, depth), 1)` | Encode: writes the 13-byte header at 1 bit per channel. |
| 5 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:294](lsb_stego/core.py#L294) | `_write(samples, _HEADER_SAMPLES, blob, depth)` | Encode: writes the payload (blob) at the chosen depth, right after the header. |
| 6 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › encode()` | [lsb_stego/core.py:302](lsb_stego/core.py#L302) | `Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)` | Encode: saves the result as a lossless PNG. |
| 7 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:265](lsb_stego/core.py#L265) | `bits = chunk & 1` | **Decode: the LSB read.** Takes the lowest bit of each R/G/B value. |
| 8 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:269](lsb_stego/core.py#L269) | `bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1` | Decode (2-bit mode): takes the two lowest bits of each value. |
| 9 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _read()` | [lsb_stego/core.py:271](lsb_stego/core.py#L271) | `return np.packbits(bits).tobytes()` | Decode: packs the bits back into bytes. |
| 10 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:319](lsb_stego/core.py#L319) | `magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))` | Decode: reads and unpacks the header (magic, flags, length, CRC). |
| 11 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:321](lsb_stego/core.py#L321) | `depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1` | Decode: gets the bit depth (1 or 2) from the header flags. |
| 12 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:324](lsb_stego/core.py#L324) | `blob = _read(carrier, _HEADER_SAMPLES, length, depth)` | Decode: reads the payload at that depth. |
| 13 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › decode()` | [lsb_stego/core.py:325](lsb_stego/core.py#L325) | `if zlib.crc32(blob) != crc:` | Decode: integrity check. A mismatch means the image was edited. |
| 14 | `crypto.py` | `LSB-Encoding-Project › lsb_stego › crypto.py › encrypt()` | [lsb_stego/crypto.py:36](lsb_stego/crypto.py#L36) | `ciphertext = AESGCM(derive_key(password, salt)).encrypt(nonce, plaintext, aad)` | Encode: AES-256-GCM encryption with a scrypt-derived key. |
| 15 | `crypto.py` | `LSB-Encoding-Project › lsb_stego › crypto.py › decrypt()` | [lsb_stego/crypto.py:45](lsb_stego/crypto.py#L45) | `return AESGCM(derive_key(password, salt)).decrypt(nonce, ciphertext, aad)` | Decode: AES-256-GCM decryption; a bad tag means a wrong password. |
| 16 | `core.py` | `LSB-Encoding-Project › lsb_stego › core.py › _decode_legacy()` | [lsb_stego/core.py:400](lsb_stego/core.py#L400) | `raw = np.packbits(red[:usable] & 1).tobytes()` | Decode (old format): reads red-channel LSBs written by the original encode.py. |

## Part 1: Encoding (hiding data in an image)

### 1. `encode()`: the main encoding function

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › encode()`
- **Lines:** [lsb_stego/core.py:276-303](lsb_stego/core.py#L276-L303)

The public entry point every caller uses. It opens the cover, builds the payload, picks 1-bit or 2-bit mode, writes the bits into the pixels and saves a PNG.

```python
276  def encode(cover: ImageSource, secret: Secret, out_path: str | os.PathLike,
277             password: str | None = None, *, max_depth: int = MAX_DEPTH) -> EncodeResult:
278      """Hide ``secret`` in ``cover`` and write a lossless PNG to ``out_path``.
279  
280      Uses 1 bit per channel when the secret fits and up to ``max_depth`` bits
281      when it doesn't. Any extension other than ``.png`` is replaced, because
282      lossy formats such as JPEG would destroy the hidden bits.
283      """
284      img = open_image(cover, for_encoding=True)
285      blob, flags = _blob(secret, password)
286      size = HEADER.size + len(blob)
287      depth = depth_needed(size, *img.size, max_depth=max_depth)
288      if depth is None:
289          raise CapacityError(size, capacity_for_size(*img.size, max_depth))
290  
291      arr = np.array(img, dtype=np.uint8)
292      samples = arr[..., :3].reshape(-1)
293      _write(samples, 0, _header(flags, blob, depth), 1)
294      _write(samples, _HEADER_SAMPLES, blob, depth)
295      arr[..., :3] = samples.reshape(arr.shape[0], arr.shape[1], 3)
296  
297      out = Path(out_path)
298      renamed = out.suffix.lower() != ".png"
299      if renamed:
300          out = out.with_suffix(".png")
301      out.parent.mkdir(parents=True, exist_ok=True)
302      Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)
303      return EncodeResult(out, size, capacity_for_size(*img.size, depth), renamed, depth)
```

**Key lines:**

- **284** `img = open_image(cover, for_encoding=True)`: opens and normalises the cover image
- **285** `blob, flags = _blob(secret, password)`: builds the payload: inner record → compress → encrypt
- **287** `depth = depth_needed(size, *img.size, max_depth=max_depth)`: picks the smallest bit depth that fits (1, else 2)
- **289** `raise CapacityError(size, capacity_for_size(*img.size, max_depth))`: raises `CapacityError` if it doesn't fit even at 2 bits
- **293** `_write(samples, 0, _header(flags, blob, depth), 1)`: header is always written at 1 bit per channel
- **294** `_write(samples, _HEADER_SAMPLES, blob, depth)`: payload written at the chosen depth
- **302** `Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)`: lossless PNG output (JPEG would destroy the bits)

### 2. `_write()`: the LSB embedding (core of encoding)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _write()`
- **Lines:** [lsb_stego/core.py:239-254](lsb_stego/core.py#L239-L254)

This is where the secret actually enters the pixels. Each R, G or B value keeps its upper bits, and its lowest 1 (or 2) bits are replaced with secret bits. NumPy does every pixel at once, so a 5 MB secret takes milliseconds.

```python
239  def _write(samples: np.ndarray, start: int, data: bytes, depth: int) -> None:
240      """Store ``data`` in the low ``depth`` bits of samples[start:], MSB first."""
241      bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
242      if depth == 1:
243          values = bits
244      else:
245          pad = (-bits.size) % depth
246          if pad:
247              bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
248          groups = bits.reshape(-1, depth)
249          values = np.zeros(groups.shape[0], dtype=np.uint8)
250          for j in range(depth):
251              values |= groups[:, j] << np.uint8(depth - 1 - j)
252      end = start + values.size
253      keep = np.uint8(0xFF ^ ((1 << depth) - 1))
254      samples[start:end] = (samples[start:end] & keep) | values
```

**Key lines:**

- **241** `bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))`: bytes → individual bits
- **251** `values |= groups[:, j] << np.uint8(depth - 1 - j)`: 2-bit mode: combine two bits per value
- **253** `keep = np.uint8(0xFF ^ ((1 << depth) - 1))`: mask that keeps the untouched upper bits (0xFE for 1-bit, 0xFC for 2-bit)
- **254** `samples[start:end] = (samples[start:end] & keep) | values`: **the write:** `(pixel & keep) | secret_bits`

### 3. `_blob()`: build the payload (compress + encrypt)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _blob()`
- **Lines:** [lsb_stego/core.py:187-193](lsb_stego/core.py#L187-L193)

Turns the secret into the bytes that get hidden, and sets the flags that tell the decoder what was done.

```python
187  def _blob(secret: Secret, password: str | None) -> tuple[bytes, int]:
188      blob, compressed = _compress(_inner_bytes(secret))
189      flags = FLAG_COMPRESSED if compressed else 0
190      if password:
191          blob = crypto.encrypt(blob, password, aad=MAGIC)
192          flags |= FLAG_ENCRYPTED
193      return blob, flags
```

### 4. `_inner_bytes()`: pack the text or file

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _inner_bytes()`
- **Lines:** [lsb_stego/core.py:165-173](lsb_stego/core.py#L165-L173)

Text is stored as UTF-8. Files keep their name, without folders, so the decoder can restore it.

```python
165  def _inner_bytes(secret: Secret) -> bytes:
166      if isinstance(secret, TextSecret):
167          kind, name, data = KIND_TEXT, b"", secret.text.encode("utf-8")
168      elif isinstance(secret, FileSecret):
169          base = Path(secret.name).name or "secret.bin"
170          kind, name, data = KIND_FILE, base[:MAX_NAME_CHARS].encode("utf-8"), secret.data
171      else:
172          raise TypeError(f"Unsupported secret type: {type(secret).__name__}")
173      return _INNER.pack(kind, len(name)) + name + data
```

### 5. `_compress()`: zlib, skipped for already-compressed data

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _compress()`
- **Lines:** [lsb_stego/core.py:176-184](lsb_stego/core.py#L176-L184)

Compresses text and documents. Photos, ZIPs and videos are detected from a 64 KB sample and stored as they are.

```python
176  def _compress(inner: bytes) -> tuple[bytes, bool]:
177      # Photos, archives and videos are already compressed: probe a sample so a
178      # multi-megabyte secret isn't run through zlib for nothing.
179      if len(inner) > 256 * 1024:
180          probe = inner[:64 * 1024]
181          if len(zlib.compress(probe, 1)) > len(probe) * 0.97:
182              return inner, False
183      packed = zlib.compress(inner, 6)
184      return (packed, True) if len(packed) < len(inner) else (inner, False)
```

### 6. `encrypt()` / `derive_key()`: password protection

- **File:** `crypto.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › crypto.py › encrypt()`
- **Lines:** [lsb_stego/crypto.py:24-37](lsb_stego/crypto.py#L24-L37)

scrypt turns the password into a 256-bit key, and AES-256-GCM encrypts the payload. The output is `salt | nonce | ciphertext+tag`.

```python
24  def derive_key(password: str, salt: bytes) -> bytes:
25      normalised = unicodedata.normalize("NFC", password).encode("utf-8")
26      return hashlib.scrypt(
27          normalised, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
28          maxmem=64 * 1024 * 1024, dklen=32,
29      )
30  
31  
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
- **Lines:** [lsb_stego/core.py:196-197](lsb_stego/core.py#L196-L197)

Writes `MAGIC | flags | length | CRC-32`. Bits 2–3 of the flags hold the bit depth.

```python
196  def _header(flags: int, blob: bytes, depth: int) -> bytes:
197      return HEADER.pack(MAGIC, flags | ((depth - 1) << DEPTH_SHIFT), len(blob), zlib.crc32(blob))
```

### 8. `capacity_for_size()` / `depth_needed()`: how much fits

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › capacity_for_size()`
- **Lines:** [lsb_stego/core.py:137-160](lsb_stego/core.py#L137-L160)

Capacity is `width × height × 3 × depth / 8` bytes. The encoder uses 1 bit when possible and 2 bits otherwise.

```python
137  def capacity_for_size(width: int, height: int, depth: int = MAX_DEPTH) -> int:
138      """Bytes (header included) that fit in an image of this size."""
139      samples = width * height * 3
140      header_samples = HEADER.size * 8
141      if samples < header_samples:
142          return samples // 8
143      return HEADER.size + (samples - header_samples) * depth // 8
144  
145  
146  def capacity(source: ImageSource, depth: int = MAX_DEPTH) -> int:
147      if isinstance(source, Image.Image):
148          width, height = source.size
149      else:
150          with Image.open(source) as img:
151              width, height = img.size
152      return capacity_for_size(width, height, depth)
153  
154  
155  def depth_needed(size: int, width: int, height: int, max_depth: int = MAX_DEPTH) -> int | None:
156      """Fewest bits per channel that fit ``size`` bytes, or None if none do."""
157      for depth in range(1, max_depth + 1):
158          if size <= capacity_for_size(width, height, depth):
159              return depth
160      return None
```

### 9. `open_image()`: prepare the cover image

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › open_image()`
- **Lines:** [lsb_stego/core.py:114-134](lsb_stego/core.py#L114-L134)

Loads any Pillow-readable picture. It applies EXIF rotation and converts grayscale and palette images to RGB/RGBA, which crashed the original script.

```python
114  def open_image(source: ImageSource, *, for_encoding: bool = False) -> Image.Image:
115      """Open ``source`` and return it as an RGB or RGBA image."""
116      if isinstance(source, Image.Image):
117          img = source
118      else:
119          try:
120              img = Image.open(source)
121              img.load()
122          except FileNotFoundError:
123              raise
124          except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
125              raise UnsupportedImageError(f"This file can't be opened as an image ({exc}).") from exc
126      if for_encoding:
127          # Bake the EXIF rotation in so the output looks the way the user saw it.
128          img = ImageOps.exif_transpose(img)
129      if img.mode in ("RGB", "RGBA"):
130          return img
131      has_alpha = img.mode in ("LA", "PA", "La") or (img.mode == "P" and "transparency" in img.info)
132      if img.mode in ("I;16", "I;16B", "I;16L", "I"):
133          img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
134      return img.convert("RGBA" if has_alpha else "RGB")
```


## Part 2: Decoding (revealing hidden data)

### 10. `decode()`: the main decoding function

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › decode()`
- **Lines:** [lsb_stego/core.py:313-344](lsb_stego/core.py#L313-L344)

The public entry point every caller uses. It reads the header, checks integrity, decrypts, decompresses and returns a `Revealed` (text or file). If there's no header, it falls back to the original format.

```python
313  def decode(source: ImageSource, password: str | None = None) -> Revealed:
314      """Extract whatever :func:`encode` (or the original ``encode.py``) hid."""
315      img = open_image(source)
316      carrier = _carrier(img)
317  
318      if carrier.size >= _HEADER_SAMPLES:
319          magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))
320          if magic == MAGIC:
321              depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1
322              if length > capacity_for_size(*img.size, depth) - HEADER.size:
323                  raise CorruptDataError("The hidden content's length is larger than the image.")
324              blob = _read(carrier, _HEADER_SAMPLES, length, depth)
325              if zlib.crc32(blob) != crc:
326                  raise CorruptDataError(
327                      "The hidden content is damaged. The image was probably edited, "
328                      "resized or re-saved in a lossy format after the data was hidden."
329                  )
330              encrypted = bool(flags & FLAG_ENCRYPTED)
331              compressed = bool(flags & FLAG_COMPRESSED)
332              if encrypted:
333                  if not password:
334                      raise PasswordRequiredError("This content is protected by a password.")
335                  blob = crypto.decrypt(blob, password, aad=MAGIC)
336              if compressed:
337                  try:
338                      inflater = zlib.decompressobj()
339                      blob = inflater.decompress(blob, MAX_DECOMPRESSED)
340                  except zlib.error as exc:
341                      raise CorruptDataError("The hidden content could not be decompressed.") from exc
342              return _parse_inner(blob, encrypted=encrypted, compressed=compressed)
343  
344      return _decode_legacy(img)
```

**Key lines:**

- **319** `magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))`: read the header at 1 bit per channel
- **320** `if magic == MAGIC:`: only trust it if the magic bytes `LSB\x02` are present
- **321** `depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1`: recover the bit depth from the flags
- **324** `blob = _read(carrier, _HEADER_SAMPLES, length, depth)`: read the payload at that depth
- **325** `if zlib.crc32(blob) != crc:`: CRC-32 integrity check
- **335** `blob = crypto.decrypt(blob, password, aad=MAGIC)`: decrypt (raises `WrongPasswordError` on a bad password)
- **339** `blob = inflater.decompress(blob, MAX_DECOMPRESSED)`: decompress, with a 1 GB safety limit
- **342** `return _parse_inner(blob, encrypted=encrypted, compressed=compressed)`: unpack into text or file
- **344** `return _decode_legacy(img)`: no header: try the old format

### 11. `_read()`: the LSB extraction (core of decoding)

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _read()`
- **Lines:** [lsb_stego/core.py:257-271](lsb_stego/core.py#L257-L271)

The exact inverse of `_write()`. It takes the lowest 1 (or 2) bits of each R, G and B value and packs them back into bytes.

```python
257  def _read(carrier: np.ndarray, start: int, count: int, depth: int) -> bytes:
258      """Inverse of :func:`_write`: ``count`` bytes from samples[start:]."""
259      nbits = count * 8
260      needed = -(-nbits // depth)
261      if start + needed > carrier.size:
262          raise CorruptDataError("The hidden content runs past the end of the image.")
263      chunk = carrier[start:start + needed]
264      if depth == 1:
265          bits = chunk & 1
266      else:
267          bits = np.empty((needed, depth), dtype=np.uint8)
268          for j in range(depth):
269              bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1
270          bits = bits.reshape(-1)[:nbits]
271      return np.packbits(bits).tobytes()
```

**Key lines:**

- **265** `bits = chunk & 1`: **the read (1-bit):** `value & 1`
- **269** `bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1`: **the read (2-bit):** shift and mask each bit
- **271** `return np.packbits(bits).tobytes()`: bits → bytes

### 12. `_carrier()`: flatten pixels into one channel stream

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _carrier()`
- **Lines:** [lsb_stego/core.py:233-236](lsb_stego/core.py#L233-L236)

Lays out every R, G and B value in reading order and skips alpha. Both `_read()` and `_write()` walk this order.

```python
233  def _carrier(img: Image.Image) -> np.ndarray:
234      """Flat uint8 array of every R, G and B sample (alpha excluded)."""
235      arr = np.asarray(img, dtype=np.uint8)
236      return arr[..., :3].reshape(-1)
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
- **Lines:** [lsb_stego/core.py:211-225](lsb_stego/core.py#L211-L225)

Reads the kind (text or file) and the file name, and returns the data as a `Revealed` object.

```python
211  def _parse_inner(inner: bytes, *, encrypted: bool, compressed: bool) -> Revealed:
212      if len(inner) < _INNER.size:
213          raise CorruptDataError("The hidden content is truncated.")
214      kind, name_len = _INNER.unpack_from(inner)
215      start = _INNER.size + name_len
216      if kind not in (KIND_TEXT, KIND_FILE) or start > len(inner):
217          raise CorruptDataError("The hidden content is malformed.")
218      name = inner[_INNER.size:start].decode("utf-8", errors="replace") or None
219      return Revealed(
220          kind="text" if kind == KIND_TEXT else "file",
221          data=inner[start:],
222          name=name,
223          encrypted=encrypted,
224          compressed=compressed,
225      )
```

### 15. `has_container()`: quick “does this image hide something?” check

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › has_container()`
- **Lines:** [lsb_stego/core.py:306-310](lsb_stego/core.py#L306-L310)

Reads only the 4 magic bytes. The GUI uses it to show *Contains hidden data* as soon as a picture is opened.

```python
306  def has_container(source: ImageSource) -> bool:
307      carrier = _carrier(open_image(source))
308      if carrier.size < _HEADER_SAMPLES:
309          return False
310      return _read(carrier, 0, len(MAGIC), 1) == MAGIC
```

### 16. `_decode_legacy()`: images made by the original `encode.py`

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py › _decode_legacy()`
- **Lines:** [lsb_stego/core.py:391-414](lsb_stego/core.py#L391-L414)

The old format: red-channel LSBs, ending in four zero bytes, with no header or checksum. Results that are neither readable text nor a known file type are only offered as a candidate.

```python
391  def _decode_legacy(img: Image.Image) -> Revealed:
392      """Read the original format: red-channel LSBs ending in four NUL bytes.
393  
394      That format has no header, so any image "decodes" to something. Results
395      that are neither readable text nor a recognisable file type are reported
396      as :class:`NoHiddenDataError` with the raw bytes attached as a candidate.
397      """
398      red = np.asarray(img, dtype=np.uint8)[..., 0].reshape(-1)
399      usable = red.size - red.size % 8
400      raw = np.packbits(red[:usable] & 1).tobytes()
401      end = raw.find(LEGACY_TERMINATOR)
402      data = raw[:end] if end > 0 else b""
403      if not data:
404          raise NoHiddenDataError()
405  
406      text = _as_printable_text(data)
407      if text is not None:
408          return Revealed("text", text.encode("utf-8"), legacy=True)
409  
410      ext = _guess_extension(data)
411      candidate = Revealed("file", data, name=f"recovered{ext or '.bin'}", legacy=True)
412      if ext is None:
413          raise NoHiddenDataError(candidate=candidate)
414      return candidate
```

**Key lines:**

- **400** `raw = np.packbits(red[:usable] & 1).tobytes()`: read red-channel LSBs into bytes
- **401** `end = raw.find(LEGACY_TERMINATOR)`: find the four-zero-byte terminator


## Part 3: Where encoding and decoding are triggered

| Trigger | File | Breadcrumbs | Line | Code |
| --- | --- | --- | --- | --- |
| GUI **Hide Data…** button | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App.hide()` | [lsb_stego/gui/app.py:752](lsb_stego/gui/app.py#L752) | `self.worker.run(lambda: core.encode(cover.source, secret, path, password), done, failed)` |
| GUI **Reveal** button / opening an image | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App.reveal()` | [lsb_stego/gui/app.py:831](lsb_stego/gui/app.py#L831) | `self.worker.run(lambda: core.decode(loaded.source, password), done, failed)` |
| GUI live *Space used* meter | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._compute_size()` | [lsb_stego/gui/app.py:660](lsb_stego/gui/app.py#L660) | `self.needed = core.container_size(secret, password)` |
| GUI 1-bit / 2-bit indicator | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › App._refresh_hide()` | [lsb_stego/gui/app.py:678](lsb_stego/gui/app.py#L678) | `depth = core.depth_needed(need, self.cover.width, self.cover.height) \` |
| GUI *Contains hidden data* label | `app.py` | `LSB-Encoding-Project › lsb_stego › gui › app.py › load_image()` | [lsb_stego/gui/app.py:151](lsb_stego/gui/app.py#L151) | `carrier_has_data = core.has_container(img)` |
| CLI `lsb-encode` / `python encode.py` | `cli.py` | `LSB-Encoding-Project › lsb_stego › cli.py › _encode()` | [lsb_stego/cli.py:76](lsb_stego/cli.py#L76) | `result = core.encode(image_path, secret, output, password or None)` |
| CLI `lsb-decode` / `python decode.py` | `cli.py` | `LSB-Encoding-Project › lsb_stego › cli.py › _decode()` | [lsb_stego/cli.py:90](lsb_stego/cli.py#L90) | `revealed = core.decode(image_path)` |
| CLI password retry | `cli.py` | `LSB-Encoding-Project › lsb_stego › cli.py › _decode()` | [lsb_stego/cli.py:92](lsb_stego/cli.py#L92) | `revealed = core.decode(image_path, getpass.getpass("🔒 Enter the password: "))` |
| Script `encode.py` | `encode.py` | `LSB-Encoding-Project › encode.py` | [encode.py:6](encode.py#L6) | `raise SystemExit(encode_main())` |
| Script `decode.py` | `decode.py` | `LSB-Encoding-Project › decode.py` | [decode.py:6](decode.py#L6) | `raise SystemExit(decode_main())` |
| Poetry command `lsb-encode` | `pyproject.toml` | `LSB-Encoding-Project › pyproject.toml › [project.scripts]` | [pyproject.toml:15](pyproject.toml#L15) | `lsb-encode = "lsb_stego.cli:encode_main"` |
| Poetry command `lsb-decode` | `pyproject.toml` | `LSB-Encoding-Project › pyproject.toml › [project.scripts]` | [pyproject.toml:16](pyproject.toml#L16) | `lsb-decode = "lsb_stego.cli:decode_main"` |

## Part 4: Format constants

### 17. Container format definitions

- **File:** `core.py`
- **Breadcrumbs:** `LSB-Encoding-Project › lsb_stego › core.py`
- **Lines:** [lsb_stego/core.py:46-61](lsb_stego/core.py#L46-L61)

The magic bytes, the header layout (`>4sBII` = magic, flags, length, CRC), the flag bits, and the 2-bit maximum depth.

```python
46  MAGIC = b"LSB\x02"
47  HEADER = struct.Struct(">4sBII")
48  _INNER = struct.Struct(">BH")
49  
50  FLAG_COMPRESSED = 0x01
51  FLAG_ENCRYPTED = 0x02
52  DEPTH_SHIFT = 2
53  DEPTH_MASK = 0x0C
54  MAX_DEPTH = 2          # used automatically when 1 bit per channel is not enough
55  KIND_TEXT = 0
56  KIND_FILE = 1
57  
58  MAX_NAME_CHARS = 255
59  PNG_LEVEL = 3          # as small as level 6 on LSB-noisy pixels, and faster
60  MAX_DECOMPRESSED = 1 << 30
61  LEGACY_TERMINATOR = b"\x00" * 4
```

