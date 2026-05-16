import { GroupSummaryType } from "../types/crawlFB_type";
import { AiFillLike } from "react-icons/ai";
import { FaRegComments } from "react-icons/fa";
import { IoShareSocialSharp } from "react-icons/io5";
export default function FacebookPosts({ mockPosts }: { mockPosts: GroupSummaryType[] }) {
    return (
        <div className="max-w-4xl mx-auto space-y-6 mt-10">
            <h1 className="text-3xl font-bold text-slate-800">Danh sách bài viết</h1>

            <div className="grid lg:grid-cols-2 gap-6">

                {mockPosts.map((post, index) => (
                    <div key={index} className="bg-white rounded-3xl shadow-lg border border-slate-200">
                        {
                            post.hot_post ?
                                <div

                                    className=" p-6 space-y-5"
                                >

                                    <div className="flex justify-between items-start">
                                        <div>
                                            <h2 className="text-xl font-bold text-slate-800">{post.group_name} </h2>
                                            <p className="text-sm text-slate-500 mt-1">🕒 {post.hot_post.date}</p>
                                        </div>
                                        <span className="px-4 py-2 bg-green-100 text-green-700 rounded-xl font-semibold">
                                            Điểm: {post.hot_post.score}
                                        </span>
                                    </div>

                                    <div>

                                        <p className="text-slate-600 mt-2 leading-7">{post.hot_post.content}</p>
                                    </div>

                                    <div className="grid md:grid-cols-3 gap-4">
                                        <div className="bg-slate-50 rounded-2xl p-4 ">
                                            <p className="text-sm text-slate-500">Tương tác</p>
                                            <div className="flex flex-col gap-x-3 mt-2">
                                                <p className="flex gap-x-2 text-sm font-bold text-slate-800">
                                                    <AiFillLike className="text-blue-500 " /> {post.hot_post.reactions}
                                                </p>
                                                <p className="flex gap-x-2 text-sm font-bold text-slate-800">
                                                    <FaRegComments className="text-black" /> {post.hot_post.comments}
                                                </p>
                                                <p className="flex gap-x-2 text-sm font-bold text-slate-800">
                                                    <IoShareSocialSharp className="text-blue-500 " /> {post.hot_post.shares}
                                                </p>
                                            </div>

                                        </div>


                                        <div className="bg-slate-50 rounded-2xl p-4 md:col-span-2">
                                            <p className="text-sm text-slate-500 mb-2">Link video</p>
                                            {post.hot_post.media_url ?
                                                <a
                                                    href={post.hot_post.media_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-violet-600 font-medium break-all hover:underline"
                                                >
                                                    {post.hot_post.media_url}
                                                </a>
                                                :
                                                <p className="text-xl font-bold text-slate-800">Không có video</p>
                                            }
                                        </div>

                                    </div>

                                    <div>
                                        <p className="text-sm font-semibold text-slate-600 mb-3">Danh sách ảnh</p>
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                            {(post.hot_post.images && post.hot_post.images.length > 0) ?
                                                post.hot_post.images.map((img, index) => (

                                                    <img
                                                        key={index}
                                                        src={img}
                                                        alt="post"
                                                        className="w-20 h-20 object-cover rounded-2xl border"
                                                    />
                                                )) :
                                                <p className="text-xl font-bold text-slate-800">Không có hình ảnh</p>

                                            }

                                        </div>
                                    </div>
                                    <div className="w-full">
                                        <a href={post.hot_post.url} target="_blank" rel="noopener noreferrer"
                                            className={
                                                [" flex items-center justify-center   text-white text-sm font-medium ",
                                                    "bg-gradient-to-r from-blue-500 to-blue-600",
                                                    "  shadow-md",
                                                    "  transition-all duration-300",
                                                    " hover:from-blue-600 hover:to-blue-700",
                                                    "hover:shadow-lg hover:scale-[1.03]",
                                                    "active:scale-95",
                                                    "rounded-lg px-3 py-2"
                                                ].join(" ")
                                            }
                                        >
                                            Xem bài viết
                                        </a>
                                    </div>

                                </div>
                                :
                                <div>
                                    <p className="text-xl font-bold text-slate-800">Không có bài viết nào</p>

                                </div>
                        }
                    </div>
                ))}

            </div>

        </div>

    );
}
