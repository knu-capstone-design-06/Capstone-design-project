/// <reference types="vite/client" />
// 상품 그림(assets/illustrations/<상품 ID>.svg)을 상품 ID로 찾습니다. 그림은 이 프로젝트에서 그린 SVG입니다.
const pictureFiles = import.meta.glob<string>('../assets/illustrations/*.svg', { eager: true, query: '?url', import: 'default' });

const pictures = new Map(Object.entries(pictureFiles).map(([path, url]) => [path.slice(path.lastIndexOf('/') + 1, -'.svg'.length), url]));

/** 상품 ID의 그림 주소입니다. 그림이 없는 상품은 null이고, 그때 타일은 분류 아이콘을 씁니다. */
export function productPicture(productId: string): string | null {
  return pictures.get(productId) ?? null;
}
