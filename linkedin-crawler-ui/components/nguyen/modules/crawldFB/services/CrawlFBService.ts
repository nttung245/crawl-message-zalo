import axiosClient from "../../../shared/api/axiosClient";
import { FetchCrawlResponse,CrawlFBRequest } from "../types/crawlFB_type";

export  const CrawlFbService=async(payload:CrawlFBRequest):Promise<FetchCrawlResponse>=>{
      const response=await axiosClient.post<FetchCrawlResponse>("/api/v1/CrawlFbForFE",payload);
      return response.data
}