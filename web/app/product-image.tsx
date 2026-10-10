import Image from "next/image";

/** Decorative catalogue illustrations, individually cropped with preserved transparency. */
const TYPES: [string, number, number][] = [
  ["ALHO", 0, 0], ["ABACATE", 0, 1], ["ABACAXI", 0, 2], ["ABOBORA", 0, 3], ["ALPERCE", 0, 4],
  ["BATATA VERMELHA", 0, 5], ["BATATA DOCE", 0, 7], ["BATATA", 0, 6], ["GENGIBRE", 0, 8],
  ["CEBOLA ROXA", 0, 10], ["CEBOLINHA", 0, 11], ["CEBOLA", 0, 9], ["BANANA PAO", 0, 13], ["BANANA", 0, 12],
  ["LARANJA", 0, 14], ["CLEMENTINA", 0, 15], ["LIMAO", 0, 16], ["LIMA", 0, 17],
  ["MELANCIA PRETA", 0, 19], ["MELANCIA MINI", 0, 20], ["MELANCIA", 0, 18], ["MELAO", 0, 21],
  ["CANTALUPE", 0, 22], ["MELOA", 0, 23], ["PINK LADY", 0, 25], ["GOLDEN", 0, 26],
  ["COSMIC", 0, 27], ["FUJI", 0, 28], ["GRANNY", 0, 29], ["REINETA", 0, 30], ["MACA", 0, 24],
  ["CONFERENCE", 0, 32], ["PERA", 0, 31], ["KIWI GOLD", 0, 34], ["KIWI", 0, 33],
  ["ALFACE", 0, 35], ["COUVE PORTUGUESA", 0, 36], ["PIMENTO VERDE", 0, 37], ["PIMENTO VERMELHO", 0, 38],
  ["BERINGELA", 0, 39], ["CHUCHU", 0, 40], ["FEIJAO", 0, 41], ["PEPINO", 0, 42],
  ["BROCOLO", 0, 43], ["COUVE BRANCA", 0, 44], ["COUVE ROXA", 0, 45], ["COUVE FLOR", 0, 46], ["CURGETE", 0, 47],
  ["TOMATE CORACAO", 1, 3], ["TOMATE MINI CHUCHA", 1, 1], ["TOMATE CHUCHA", 1, 1],
  ["TOMATE CHERRY", 1, 2], ["MINI TOMATE", 1, 2], ["TOMATE CACHO", 0, 48], ["TOMATE", 1, 0],
  ["MORANGO", 1, 4], ["MANGA AVIAO", 1, 16], ["MANGA", 1, 5], ["UVA BRANCA", 1, 6], ["UVA", 1, 7],
  ["CEREJA", 1, 8], ["PITAYA AMARELA", 1, 10], ["PITAYA", 1, 9], ["GOIABA", 1, 11], ["MARACUJA", 1, 12],
  ["GRANADILHA", 1, 13], ["MAMAO", 1, 14], ["PAPAIA", 1, 15], ["PESSEGO PARAGUAYO", 1, 17],
  ["PESSEGO", 1, 18], ["NECTARINA", 1, 19],
];

export function productSprite(name: string) {
  const normalized = name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
  const match = TYPES.find(([type]) => normalized.includes(type));
  return { sheet: match?.[1] ?? 1, index: match?.[2] ?? 20 };
}

function productImageSrc(name: string) {
  const { sheet, index } = productSprite(name);
  return `/products/p${sheet}-${index}.webp`;
}

// Keep decoded thumbnails ready before the product list mounts. A bounded queue
// prevents thumbnail requests from flooding the connection used by camera feeds.
const warmed = new Map<string, HTMLImageElement>();
const pending: string[] = [];
let active = 0;

function warmNext() {
  while (active < 6 && pending.length) {
    const src = pending.shift()!;
    const image = warmed.get(src)!;
    active++;
    const finish = () => { active--; warmNext(); };
    image.onload = () => { void image.decode().catch(() => undefined).then(finish); };
    image.onerror = () => { warmed.delete(src); finish(); };
    image.src = src;
  }
}

export function preloadProductImages(names: string[]) {
  if (typeof window === "undefined") return;
  for (const name of names) {
    const src = productImageSrc(name);
    if (warmed.has(src)) continue;
    const image = new window.Image();
    image.decoding = "async";
    image.fetchPriority = warmed.size < 8 ? "auto" : "low";
    warmed.set(src, image);
    pending.push(src);
  }
  warmNext();
}

export function ProductImage({ name }: { name: string }) {
  return (
    <Image
      alt=""
      className="product-image"
      src={productImageSrc(name)}
      width={56}
      height={56}
      loading="eager"
      decoding="async"
      unoptimized
    />
  );
}
