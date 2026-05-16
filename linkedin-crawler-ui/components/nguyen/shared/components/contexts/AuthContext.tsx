"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface AuthUser {
  email: string;
  password: string,
  idFacebook?: string,
  name?: string,
  isAuthenticated: boolean;
}

interface AuthContextType {
  user: AuthUser | null;
  saveUserSession: (email: string,password:string) => void;
  logout: () => void;
  updateUser: (newData: Partial<AuthUser>) => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true); // <--- Mặc định ban đầu là đang load
  // Khôi phục session từ localStorage khi load trang
  useEffect(() => {
    const storedUser = localStorage.getItem("crawl_fb_user");
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch (error) {
        console.error("Lỗi parse session:", error);
        localStorage.removeItem("crawl_fb_user");
      }
    }
    setIsLoading(false); // <--- Đọc xong thì tắt loading
  }, []);


  const saveUserSession = (email: string, password: string) => {
    const sessionData = { email, isAuthenticated: true, password };
    setUser(sessionData);
    localStorage.setItem("crawl_fb_user", JSON.stringify(sessionData));
  };
  const updateUser = (newData: Partial<AuthUser>) => {
    setUser((prevUser) => {
      if (!prevUser) return null;

      const updatedUser = { ...prevUser, ...newData };
      
      // Cập nhật lại cả vào LocalStorage để khi F5 không bị mất
      localStorage.setItem("crawl_fb_user", JSON.stringify(updatedUser));
      
      return updatedUser;
    });
  }

  const logout = () => {
    setUser(null);
    localStorage.removeItem("crawl_fb_user");
  };

  return (
    <AuthContext.Provider value={{ user,updateUser, isLoading, saveUserSession, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuthContext = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuthContext must be used within an AuthProvider");
  return context;
};