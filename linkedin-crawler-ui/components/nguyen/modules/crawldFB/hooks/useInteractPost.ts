import { useState } from "react";
import { toast } from "sonner";
import { interactPostService } from "../services/createInteractionService";
import { InteractionPayload } from "../schemas/Interaction_schemas";

export function useInteractPost() {
    const [isLoading, setIsLoading] = useState(false);

    const submitInteraction = async (data: InteractionPayload) => {
        setIsLoading(true);
        try {
            const result = await interactPostService(data);
            
            if (result.success === "success") {
                toast.success("Tương tác thành công!");
                return result;
            } else {
                toast.error(result.message || "Có lỗi xảy ra khi tương tác!");
                return null;
            }
        } catch (error) {
            toast.error("Có lỗi xảy ra khi kết nối đến server!");
            return null;
        } finally {
            setIsLoading(false);
        }
    };

    return {
        isLoading,
        submitInteraction
    };
}