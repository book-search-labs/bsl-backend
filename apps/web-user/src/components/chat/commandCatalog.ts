export type ChatCommandCategory = {
  title: string
  examples: string[]
}

export const CHAT_COMMAND_CATALOG: ChatCommandCategory[] = [
  {
    title: '도서 검색',
    examples: ['"문화" 검색 결과 줘', '김정욱 책 검색해줘', 'ISBN 9788937462674 책 찾아줘'],
  },
  {
    title: '추천',
    examples: ['장바구니 기준 추천해줘', '이 책과 비슷한 책 추천해줘', '연구 주제로 책 추천해줘'],
  },
  {
    title: '주문/배송 조회',
    examples: ['내 주문목록 보여줘', '배송 조회 해줘', '주문 12 상태 알려줘', '배송 언제와?'],
  },
  {
    title: '취소/환불',
    examples: ['환불 조건 알려줘', '주문 취소 가능해?', '환불 요청 진행해줘'],
  },
  {
    title: '정책/도움말',
    examples: ['배송 정책 알려줘', '결제 수단 정책 알려줘', '어떤 명령어 입력할 수 있어?'],
  },
]
