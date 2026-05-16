// src/modules/interaction/services/interaction.service.ts
import axiosClient from "@/components/nguyen/shared/api/axiosClient";
import { InteractionItemDTO, GetInteractionsResponse } from "../types/interaction.type";

export const getInteractionsService = async (): Promise<InteractionItemDTO[]> => {
    const response = await axiosClient.get<GetInteractionsResponse>("/api/v1/user-scores");
    
    return response.data.data || [];
};