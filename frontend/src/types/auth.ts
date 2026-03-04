export interface User {
    email: string;
    username: string;
    is_verified: boolean;
    is_admin?: boolean;
}

export interface JwtPayload {
    sub: string;
    username: string;
    is_admin: boolean;
    is_verified: boolean;
    iat: number;
    exp: number;
}
