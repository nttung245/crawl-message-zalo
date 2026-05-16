

export interface InteractionItemDTO {
    id: string | number;      // Định danh duy nhất từ Backend
    name: string;             // Tên người dùng (vd: "Thu Hương AI")
    scorePerWeek: number;   // Điểm số tương tác trong tuần (vd: 100)
}

export interface GetInteractionsResponse {
    status: string;
    data: InteractionItemDTO[];
}
