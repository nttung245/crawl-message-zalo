// src/modules/interaction/hooks/useGetInteractions.ts
import { useState, useCallback } from "react";
import { InteractionItemDTO } from "../types/interaction.type";
import { getInteractionsService } from "../services/getInteractionService";

export const useGetInteractions = () => {
    const [interactions, setInteractions] = useState<InteractionItemDTO[]>([]);
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const fetchInteractions = useCallback(async () => {
        setIsLoading(true);
        setError(null);

        try {
            const data = await getInteractionsService();
            
            // Sắp xếp giảm dần theo điểm số
            const sortedData = data.sort((a, b) => b.scorePerWeek - a.scorePerWeek);
            
            setInteractions(sortedData);
        } catch (err: any) {
            setError(err?.response?.data?.message || "Lỗi tải dữ liệu tương tác.");
        } finally {
            setIsLoading(false);
        }
    }, []);

    return {
        interactions,
        isLoading,
        error,
        fetchInteractions,
    };
};