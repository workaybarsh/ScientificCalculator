# Scientific Calculator Kullanım Kılavuzu

> Sürüm 1.0.2

Scientific Calculator, Windows için çevrimdışı çalışan bağımsız bir hesaplama aracıdır. Klasik bilimsel hesap makinesi yerleşiminden yararlanır; bir emülatör, firmware kopyası veya herhangi bir üreticiyle bağlantılı ürün değildir.

Bu kılavuz, ilk hesaplamadan gelişmiş modlara kadar günlük kullanım için hazırlanmıştır.

## İçindekiler

1. [Hızlı başlangıç](#hızlı-başlangıç)
2. [Temel tuşlar ve yazım](#temel-tuşlar-ve-yazım)
3. [Calculate modu](#calculate-modu)
4. [İntegral, türev, toplam ve SOLVE](#integral-türev-toplam-ve-solve)
5. [Sonuç biçimi, bellek ve geçmiş](#sonuç-biçimi-bellek-ve-geçmiş)
6. [Özel hesap modları](#özel-hesap-modları)
7. [Spreadsheet, Table ve Equation araçları](#spreadsheet-table-ve-equation-araçları)
8. [SETUP, skin ve kayıt](#setup-skin-ve-kayıt)
9. [Hata mesajları ve sorun giderme](#hata-mesajları-ve-sorun-giderme)

---

## Hızlı başlangıç

1. Uygulamayı başlatın.
2. Başlangıç modu olan **Calculate** açıkken ifadeyi ekrandaki tuşlarla veya LCD giriş alanına yazarak girin.
3. Sonucu almak için `=` tuşuna basın.
4. Mod değiştirmek için `MENU` tuşuna basın ve istediğiniz çalışma alanını seçin.

İlk denemeler için aşağıdaki ifadeleri girebilirsiniz:

| Amaç | Girdi | Beklenen sonuç |
|---|---|---|
| Dört işlem | `12+8×3` | `36` |
| Üs | `2^10` | `1024` |
| Kök | `sqrt(144)` | `12` |
| Trigonometri | `sin(π/2)` | `1` (RAD modunda) |
| Kesir | `1/3+1/6` | `1/2` |
| İmplicit multiplication | `2x` | `2×x` olarak yorumlanır |

> Varsayılan açı birimi **RAD**’dir. `sin(90)` sonucunun `1` olması için önce SETUP içinden açı birimini **DEG** yapın.

---

## Temel tuşlar ve yazım

### `SHIFT` ve `ALPHA`

- **SHIFT**: Tuşların sarı ikinci işlevlerini açar. Örneğin `SHIFT + CALC` ile `SOLVE`, `SHIFT + ∫` ile türev, `SHIFT + x` ile toplam açılır.
- **ALPHA**: Kırmızı değişken/işaret işlevlerini açar. `A`–`F`, `M`, `x`, `y` ve kırmızı `=` bu katmandadır.
- İşlev uygulandıktan sonra SHIFT/ALPHA durumu normalde otomatik kapanır.

### İfade yazım kuralları

| İşlem | Yazım | Not |
|---|---|---|
| Toplama / çıkarma | `+`, `-` | Negatif sayı için de `-` kullanın. |
| Çarpma / bölme | `×`, `÷`, `*`, `/` | Klavyeden `*` ve `/` da kullanılabilir. |
| Üs | `^` | Örnek: `3^4`. |
| Karekök / küpkök | `sqrt(9)`, `cbrt(8)` | Fonksiyon parantezi kapatılmalıdır. |
| Mutlak değer | `Abs(-5)` | `SHIFT + (` tuşuyla eklenebilir. |
| Faktöriyel | `factorial(5)` | `SHIFT + x⁻¹` ile eklenir. |
| Pi, Euler ve sanal birim | `π`, `e`, `i` | `pi` ifadesi de tanınır. |
| Önceki sonuç | `Ans` | Yeni ifade içinde önceki sonucu kullanır. |
| İmplicit multiplication | `2x`, `(x+1)(x-1)` | Açık `×` yazmak zorunda değilsiniz. |

Fonksiyonlarda parantez kullanın: `sin(π/6)`, `log(100)`, `ln(e)`. Açı birimi trigonometrik fonksiyonlara doğrudan uygulanır.

### Düzenleme ve geçmiş

- `DEL`: İmlecin solundaki karakteri siler.
- `AC`: Devam eden hesabı anında iptal eder. Calculate ve Complex modunda ekranı temizler; diğer tüm modlarda o modun yönlendirme ekranını yeniden açar. Kayıtlı ayarları silmez.
- `▲` / `▼`: Normal ifade alanında daha önce hesaplanan ifadeler arasında gezinir. `MENU` → `History`, son 10 ifade ve sonucu ayrı pencere açmadan LCD üzerinde gösterir; listede `▲` / `▼` ile gezilir.
- `SHIFT + AC` / OFF: Ayarları kaydederek uygulamayı kapatır.
- `ON`: Uygulamayı normal kapatıp yeniden açar. Kayıtlı Setup/UI ayarlarını korur; ayar veritabanını veya Spreadsheet'i ON'a özel olarak temizlemez.

`Calculating…` görünürken yalnız `AC` veya Escape kabul edilir. Bu tuşlar tek hesaplama sürecini anında iptal eder; iptal edilen sonuç `Ans` veya geçmişe yazılmaz. Hesaplama 30 saniyeyi aşarsa kontrollü zaman aşımı uygulanır ve sonuç yine kaydedilmez.

---

## Calculate modu

Calculate modu; standart, bilimsel ve sembolik hesaplamaların ana çalışma alanıdır.

### Günlük hesaplamalar

İfadeyi girip `=` tuşuna basın. Uygulama mümkün olduğunda kesin sonucu korur.

```text
(5/12)+(1/4)     → 2/3
sqrt(2)^2        → 2
sin(π/4)^2       → 1/2
```

`SHIFT + =` yaklaşık/ondalık değerlendirme yapar. Böylece kesin görünen sonucu seçili sayı biçimine göre ondalık olarak inceleyebilirsiniz.

### Geçmiş

Hesap makinesi integral, türev, toplam ve SOLVE dahil son 10 başarılı hesaplamayı ve ekranda gösterilen sonuçlarını yerel olarak saklar. `MENU` → `History` seçildiğinde liste ayrı pencere açmadan mevcut LCD’de görünür; en yeni kayıt `1`, ondan önceki kayıt `2` olarak başlar. Her satırda işlem, `=` ve sonuç birlikte görünür; `▲` / `▼` ile kayıtlar arasında gezilir, `AC` ile normal hesap ekranına dönülür. **Reset to Defaults**, Setup ayarlarıyla birlikte bu geçmişi de siler. İntegral girişinde `sinxcosx`, `sin(x)×cos(x)` olarak kabul edilir.

### Bilimsel fonksiyonlar

Kullanılabilen yaygın fonksiyonlar şunlardır:

- `sin`, `cos`, `tan` ve tersleri `asin`, `acos`, `atan`
- Hiperbolik fonksiyonlar
- `log`, `ln`, `10^(...)`, `e^(...)`
- `sqrt`, `cbrt`, `Abs`
- `factorial`, `nPr`, `nCr`

Örnekler:

```text
log(1000)         → 3
ln(e^2)           → 2
nCr(10,3)         → 120
```

`SHIFT + ×` ile `nPr`, `SHIFT + ÷` ile `nCr` giriş penceresini açabilirsiniz.

### Sabitler ve dönüşümler

- `SHIFT + 7`: Fiziksel/matematiksel sabitler penceresi.
- `SHIFT + 8`: Birim dönüşümleri penceresi.
- `SHIFT + 9`: Hesap makinesi ayarlarını varsayılanlara döndürme penceresi.

Sabitler penceresi, değerleri açıkça **CODATA 2010 legacy compatibility dataset** olarak etiketler. Bu veri seti uyumluluk amacıyla korunur; en güncel CODATA tavsiyelerinin tümünü temsil ettiği iddiasında değildir.

---

## İntegral, türev, toplam ve SOLVE

### İntegral ve türev (`∫`)

**Calculate** modunda `∫`, ayrı bir pencere açmadan yalnız LCD üzerinde çalışan işlem seçiciyi açar. `◀` / `▶` ile işlemi seçin; alanlarda ilerlemek veya hesaplamak için `=` kullanın. Seçicide belirli/belirsiz integral, sembolik türev, çift/üç katlı integral, skaler/vektörel çizgisel integral ile skaler yüzey ve akı integrali bulunur.

**Definite Integral** seçildiğinde alışılmış hesap makinesi şablonu görünür:

1. Fonksiyonu yazın.
2. `▲` ile üst sınıra, `▼` ile alt sınıra geçin.
3. Diferansiyel değişkeni alanına ulaşmak için `TAB` kullanın.
4. `=` ile hesaplayın.

Her iki sınırı da girerseniz belirli integral alınır:

```text
∫₀^π sin(x) dx  → 2
```

Yakınsak uygunsuz integral sınırları için `inf`, `∞`, `-inf` veya `-∞` yazabilirsiniz:

```text
∫₀^∞ exp(-x) dx  → 1
```

Bilinen iç tekillikler ayrı parçalarda değerlendirilir. Iraksak integral Math ERROR verir; Cauchy asal değeri sıradan integral sonucu olarak sessizce kabul edilmez.

Sembolik integral ve `+ C` sonucu için **Indefinite Integral** seçin:

```text
∫ x^2 dx  → x^3/3 + C
```

Çok katlı integral formlarında her diferansiyel değişkeni, entegrasyon sırası ve sınır ayarlanabilir. Bu sınırlar sonlu olmalıdır; iç sınır yalnız dış integrallerin değişkenlerini kullanabilir. Skaler çizgisel integral `f(x,y)`, `x(t)` ve `y(t)` kullanır; vektörel çizgisel integral `P dx + Q dy` biçimindedir. Yüzey formları parametreli `r(u,v)` yamasını ve sonlu parametre sınırlarını kullanır. Akı integralinde normal yönü olarak `r_outer × r_inner` veya tersi seçilir.

### Türev

Sembolik türev için `∫` seçicisinden **Indefinite Derivative** seçin. `SHIFT + ∫` türev şablonuna kısayoldur: nokta alanı boşsa sembolik türev, girilirse o noktadaki sayısal türev hesaplanır.

Örnekler:

```text
d/dx x^3       → 3x^2
d/dx x^2 | x=3 → 6
```

### Toplam (Σ)

`SHIFT + x` ile toplam penceresini açın. Fonksiyonu, değişkeni, başlangıç ve bitiş değerlerini girin.

Örnek: `Σ(k, k=1..10)` sonucu `55` olur.

### SOLVE / kök bulma

Calculate modunda `SHIFT + CALC` ile SOLVE açılır.

1. Bir denklemi ifade alanına yazın. Örnek: `x^2-2=0`.
2. Çözmek istediğiniz değişkeni seçin.
3. İstendiğinde başlangıç tahminini girin.

Örnek:

```text
x^2-2=0, x için başlangıç tahmini 1  → yaklaşık 1.41421356
```

Birden fazla harfli ifade yerine değişken olarak `x`, `y`, `A`–`F` gibi tek harfli tanımları kullanın. SOLVE, gerçek ve doğrulanabilir bir kök bulunamazsa hata verir.

---

## Sonuç biçimi, bellek ve geçmiş

### Sonuç görünümü

SETUP içinden aşağıdakileri değiştirebilirsiniz:

- **Input / Output**: Matematiksel veya satır biçimli giriş/çıkış.
- **Number Format**: `Norm`, `Fix`, `Sci`.
- **Number Digits**: 0–9 basamak.
- **Fraction Result**: `d/c` veya `a b/c`.
- **Complex**: `a+bi` veya kutupsal `r∠θ`.
- **Decimal Mark**: Nokta ya da virgül.
- **Digit Separator**: Büyük sayılarda ayraç gösterimi.

Kesir/köklü bir sonucu ondalık görmek için `S⇔D` tuşunu kullanın. `SHIFT + S⇔D`, uygun kesirlerde karma kesir gösterimine geçer.

### Bellek

- `STO`: Sonucu `A`, `B`, `C`, `D`, `E`, `F`, `M`, `x` veya `y` belleğine kaydeder.
- `SHIFT + STO`: Bellekten çağırma penceresi.
- `M+` / `M−`: Sonucu M belleğine ekler veya çıkarır.
- `Ans`: Son başarılı sonuca başvurur.

Örnek:

1. `25` hesaplayın.
2. `STO` ile `A` seçin.
3. `A×4` girin.
4. Sonuç `100` olur.

---

## Özel hesap modları

`MENU` tuşundan aşağıdaki modlara erişin.

Matrix, Vector, Statistics, Distribution, Spreadsheet, Table, Equation / Function,
Inequality ve Ratio, ayrı bir pencere açmadan doğrudan hesap makinesinin LCD
ekranında çalışır. Formlarda etkin değeri yazıp `=` ile ilerleyin veya hesaplayın;
`▲`/`▼` alan ya da sonuç satırını değiştirir, `◀`/`▶` numaralı seçimi veya
Spreadsheet hücresini değiştirir, `OPTN` başka işlem seçtirir ve `AC` geçerli
formu baştan başlatır. **SETUP**, `SHIFT + MENU` ile açılan ayrı ayar penceresi
olarak kalır.

### Complex

Karmaşık ifadeler için **Complex** modunu seçin. `i` sanal birimini kullanın; `SHIFT + ENG` kutupsal açı işaretini `∠` ekler.

```text
(1+i)^2          → 2i
3∠(π/2)          → karmaşık karşılığı
```

Sonuç biçimini SETUP > **Complex** seçeneğiyle `a+bi` veya `r∠θ` yapabilirsiniz.

**Complex** modunda `∫`, `OPTN` veya ayrı pencere kullanmadan LCD üzerindeki karmaşık integral seçiciyi açar. Karmaşık belirli/belirsiz integral, karmaşık çift katlı integral veya kontur integrali seçilir; sonra diferansiyel değişkenler, sıra ve sınırlar LCD alanlarında ayarlanır. Karmaşık çift katlı integralin sınırları da sonlu iç içe sınır kuralına uyar. Kontur integrali `f(z)`, parametreli `z(t)` yolu, karmaşık değişken, reel parametre ve sonlu parametre sınırlarını ister. Örneğin `f(z)=1/z`, `z(t)=exp(i*t)`, `0`–`2*pi` sonucu `2πi` olur. Kutbun üzerinden geçen yol reddedilir.

### Base-N

Base-N, 32 bit işaretli tamsayı işlemleri içindir. Seçili tabana göre sonuç o tabanda gösterilir.

| Tuş | Base-N işlevi |
|---|---|
| `x²` | DEC (10) |
| `x^` | HEX (16) |
| `log` | BIN (2) |
| `ln` | OCT (8) |

Örnekler:

```text
HEX: A+1          → B
BIN: 1010+1       → 1011
```

Farklı tabandaki sabitleri açıkça belirtmek için `h`, `b`, `o`, `d` öneklerini kullanabilirsiniz: `hFF+b1`. Mantıksal işlemler (`and`, `or`, `xor`, `xnor`, `not`) de desteklenir. Ondalıklı değerler Base-N modunda geçerli değildir.

### Matrix

Matrix LCD formunda `MatA`–`MatD` tanımlanabilir; boyut sınırı 1×1 ile 4×4 arasındadır.

1. **Define/Edit Matrix** seçin.
2. Matris adını ve satır/sütun sayısını girin.
3. Elemanları istenen sırayla girin.
4. `+`, `−`, `×`, determinant, ters, transpoz, kare, küp veya mutlak değer işlemlerini seçin.

`MatAns`, son matris sonucunu saklar ve başka bir matrise kopyalanabilir. Ters/determinant için matrisin kare; ters için ayrıca tekil olmaması gerekir.

### Vector

`VctA`–`VctD` için iki veya üç bileşenli vektörler tanımlanabilir. LCD formu bileşenleri sırayla ister.

Desteklenen işlemler:

- Toplama ve çıkarma
- Skaler çarpma
- Dot product
- Cross product
- Vektör büyüklüğü (`Abs`)
- Birim vektör
- İki vektör arasındaki açı

Sıfır vektörün birim vektörü veya açısı tanımsızdır.

### Statistics

**1-Variable** seçeneğinde x verilerini boşluk, virgül, noktalı virgül veya yeni satırla ayırarak girin.

```text
1, 2, 3, 4
```

Çıktıda `n`, toplam, kareler toplamı, ortalama, popülasyon/örneklem varyansı ve standart sapması, min–maksimum ve çeyrekler görünür.

SETUP > **Statistics Frequency** açıksa ikinci alana her veri için negatif olmayan tamsayı frekans girin. Örneğin x: `10,20,30`; frekans: `2,1,3`.

Regresyon için türü seçin (**Linear**, **Quadratic**, **Logarithmic**, **e Exponential**, **ab Exponential**, **Power**, **Inverse**) ve x/y dizilerini girin. Logaritmik ve güç modellerinde pozitiflik koşullarını gözetin.

### Distribution

Distribution modunda aşağıdaki hesaplar bulunur:

- Normal PD / Normal CD / Inverse Normal
- Binomial PD / Binomial CD
- Poisson PD / Poisson CD

Formdaki alanları sırayla girin. `sigma` pozitif olmalı; Binomial için `N` ve `x` tamsayı, `p` ise 0–1 arasında olmalıdır. Poisson için `lambda` negatif olamaz.

---

## Spreadsheet, Table ve Equation araçları

### Spreadsheet

Spreadsheet LCD alanı `A1:E45` aralığını sağlar. Satırlar için `▲`/`▼`, sütunlar için `◀`/`▶` kullanın; değer veya `=` ile başlayan formülü LCD’ye yazıp `=` ile kaydedin.

1. Ok tuşlarıyla hedef hücreye gidin.
2. Değer ya da `=` ile başlayan formülü LCD’ye girin.
3. `=` tuşuyla hücreyi kaydedin; araçlar için `OPTN` kullanın.

Örnek:

```text
A1: 10
A2: 20
B1: =A1+A2
```

Kullanılabilen araçlar:

- **Delete / Delete All**
- **Copy & Paste / Cut & Paste**
- **Fill**: Bir aralığa değer veya formül yayma
- **Recalculate**: Manuel hesaplama
- **Insert reference**: Seçili kaynak hücreyi, hedef hücreyi ve referanstan önceki formül metnini girerek referans oluşturma. Örneğin kaynak `A1` ve `=1+` öneki hedefte `=1+A1` üretir.
- **Free Space**: Kalan hücre depolama alanını gösterme

SETUP içindeki **Spreadsheet Auto Calc** kapalıysa formüller yalnız Recalculate ile yenilenir. **Spreadsheet Show Cell** ile hücrede formül veya hesaplanan değer gösterimini seçebilirsiniz.

### Table

Table modu, bir veya iki fonksiyon için değer tablosu üretir.

1. `f(x)` girin; SETUP’ta iki fonksiyon seçiliyse `g(x)` de girin.
2. Başlangıç, bitiş ve adım değerlerini girin.
3. Tabloyu inceleyin.

Örnek:

```text
f(x)=x^2, başlangıç=-1, bitiş=1, adım=0.5
```

Adım `0` olamaz ve yönü başlangıç/bitiş aralığıyla uyumlu olmalıdır.

### Equation / Function

- **Simul Equation**: 2–4 bilinmeyenli doğrusal denklem sistemi çözümü.
- **Polynomial**: 2.–4. derece polinom kökleri; ikinci derecede tepe noktası da gösterilir.
- **Differential Equation**: Birinci veya ikinci dereceden sembolik adi diferansiyel denklem çözümü. LCD formunda bağımlı ve bağımsız değişkeni seçin; `dy/dx=y` veya `d2y/dx2+y=0` gibi bir denklem girin. Başlangıç koşulları isteğe bağlıdır: birinci derecede `y(x0)`, ikinci derecede buna ek olarak `y'(x0)` girilir.

Katsayıları istenen sırayla virgülle girin. Örneğin `x²-5x+6` için katsayılar `1,-5,6` olur.

### Inequality

2.–4. derece polinom eşitsizlikleri için dereceyi, katsayıları ve ilişkiyi (`>`, `<`, `≥`, `≤`) girin. Sonuç aralık/simge biçiminde gösterilir.

### Ratio

İki oran şablonu desteklenir:

```text
A:B = X:D
A:B = C:X
```

Bilinen üç değeri girin; uygulama `X` değerini hesaplar.

---

## SETUP, skin ve kayıt

`SHIFT + MENU` ile **SETUP** penceresini açın. Başlıca seçenekler:

| Ayar | Açıklama |
|---|---|
| Angle Unit | DEG, RAD veya GRA |
| Number Format / Digits | Norm, Fix, Sci ve 0–9 basamak |
| Fraction Result | Basit ya da karma kesir |
| Complex | Dikdörtgen veya kutupsal gösterim |
| Calculator Skin | Graphite, Blue, Pink veya White |
| UI Scale | 25, 50, 75, 100, 125, 150 veya 200% |
| Decimal Mark / Digit Separator | Yerel sayı yazımı |
| Spreadsheet / Table ayarları | Otomatik hesaplama, gösterim ve tek/çift fonksiyon |

**Save** ayarları yerel Windows kullanıcı profilinde uygulamanın SQLite veritabanında saklar: normalde `%LOCALAPPDATA%\ScientificCalculator\settings.db`, `LOCALAPPDATA` yoksa sabit yedek yol olan `%USERPROFILE%\.scientific_calculator\ScientificCalculator\settings.db` kullanılır. Aynı veritabanı son 10 hesaplamanın ifadesini ve ekranda gösterilen sonucunu da tutar. Uygulamayı pencerenin kapatma düğmesiyle veya `SHIFT + AC` ile kapatmak da geçerli ayarları kaydeder. Kaldırıcı bu sabit uygulama-verisi yollarının ikisini de siler; yeniden kurulum temiz başlar.

**Reset to Defaults** kaydedilmiş ayarları ve hesap geçmişini temizler, sonra başlangıç değerlerine döner. Bu işlem yalnız Setup içinden yapılır; `ON` ile ortak bir kod yolu yoktur.

Ayarlar ve hesap geçmişi tek bir SQLite transaction içinde kaydedilir. Kaydetme veya sıfırlama başarısız olursa SETUP penceresi kullanılabilir kalır ve LCD'de `Settings ERROR` görünür; uygulama başarı bildirimi vermez.

> 125% ve üzeri UI ölçekleri küçük ekranlarda daha fazla dikey alan isteyebilir. En rahat kullanım için ekran çözünürlüğünüze uygun ölçeği seçin.

---

## Hata mesajları ve sorun giderme

Hesaplama, giriş ve ayar hataları ayrı bir hata penceresi açmadan doğrudan calculator LCD'sinde gösterilir. Aktif giriş temizlenir, mod korunur; `Ans` ve History son başarılı değerlerinde kalır. Kullanıcıya görünen tüm hata metinleri İngilizcedir; eski motor metinleri LCD'ye aktarılmadan önce çevrilir.

| Mesaj | Anlamı ve çözüm |
|---|---|
| `Syntax ERROR` | Parantezleri, fonksiyon adını ve işlem işaretlerini kontrol edin. |
| `Math ERROR` | Tanımsız işlem, geçersiz alan veya sonlu olmayan sonuç oluştu. Örneğin sıfıra bölme. |
| `Dimension ERROR` | Matris/vektör boyutları veya Spreadsheet adresleri uyumsuz. |
| `Argument ERROR` | Zorunlu alan, geçerli sınır veya doğru veri türü eksik. |
| `Cannot Solve` | SOLVE için gerçek/doğrulanabilir kök bulunamadı; farklı başlangıç tahmini deneyin. |
| `Range ERROR` | Table veya sayısal giriş aralığı geçersiz. |

Sorun yaşarsanız şu sırayı deneyin:

1. Modun doğru olduğundan emin olun.
2. Açı birimini kontrol edin.
3. Parantezleri ve fonksiyonların argümanlarını yeniden kontrol edin.
4. `AC` ile geçerli ifadeyi temizleyip yeniden girin.
5. Gerekirse SETUP içinden ayarları varsayılanlara döndürün.

## Güvenlik ve gizlilik

Uygulama normal hesaplamalar için çevrimdışı çalışır. Matematiksel ifade ayrıştırıcısı yalnız izin verilen hesaplama söz dizimini kabul eder; Python kodu veya sistem komutu çalıştırmaz.

Yayın dosyalarını her zaman resmi GitHub release sayfasından indirin. İndirilen EXE veya installer dosyasını `SHA256SUMS.txt` içindeki değerlerle doğrulayabilirsiniz.
