import axiosClient from "../../../shared/api/axiosClient";
import { DataFBResponse } from "../types/dataFb.type";
interface responseData {
    data: DataFBResponse[],

    message: string
    status: "success"
}
export const getDataFbService = async (): Promise<responseData> => {
    const response = await axiosClient.get<responseData>("/api/v1/Posts");
    return response.data
}
