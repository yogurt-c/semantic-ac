/**
 * `crypto.randomUUID()`가 없는 구형 환경(비보안 컨텍스트, 구형 브라우저)을 위한 폴백을 둔
 * 세션 ID 발급기. 보안 토큰이 아니라 AI 배치 엔진의 co-occurrence 학습이 "같은 세션에서
 * 함께 selected된 키워드"를 묶기 위한 상관키일 뿐이므로 암호학적 강도는 필요 없다.
 */
export function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
