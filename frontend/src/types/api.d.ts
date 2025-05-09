/**
 * This file was auto-generated by openapi-typescript.
 * Do not make direct changes to the file.
 */

export interface paths {
    "/api/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Search */
        get: operations["search_api_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Admin Login */
        post: operations["admin_login_api_admin_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/objects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Objects */
        get: operations["list_objects_api_admin_objects_get"];
        put?: never;
        /** Create Object */
        post: operations["create_object_api_admin_objects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/objects/{object_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Object */
        put: operations["update_object_api_admin_objects__object_id__put"];
        post?: never;
        /** Delete Object */
        delete: operations["delete_object_api_admin_objects__object_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Events */
        get: operations["get_events_api_admin_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/events/{id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Resolve Event */
        put: operations["resolve_event_api_admin_events__id__resolve_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/images/{image_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Image */
        get: operations["get_image_api_images__image_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/image-sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Image Sources */
        get: operations["list_image_sources_api_admin_image_sources_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/images/{image_id}/thumbnail": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Thumbnail */
        get: operations["get_thumbnail_api_images__image_id__thumbnail_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AdminEventSchema */
        AdminEventSchema: {
            /** Id */
            id: number;
            /** Object Id */
            object_id: number | null;
            /** Message */
            message: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Is Resolved */
            is_resolved: boolean;
        };
        /** Body_admin_login_api_admin_login_post */
        Body_admin_login_api_admin_login_post: {
            /** Grant Type */
            grant_type?: string | null;
            /** Username */
            username: string;
            /** Password */
            password: string;
            /**
             * Scope
             * @default
             */
            scope: string;
            /** Client Id */
            client_id?: string | null;
            /** Client Secret */
            client_secret?: string | null;
        };
        /** Body_create_object_api_admin_objects_post */
        Body_create_object_api_admin_objects_post: {
            /** Text Content */
            text_content: string;
            /** Image Path */
            image_path: string;
            /** Image Key */
            image_key: string;
            /** Image Source Id */
            image_source_id?: number | null;
            /** Image File */
            image_file?: string | null;
            /** Image File Sha512 */
            image_file_sha512?: string | null;
        };
        /** Body_update_object_api_admin_objects__object_id__put */
        Body_update_object_api_admin_objects__object_id__put: {
            /** Text Content */
            text_content: string;
            /** Image Path */
            image_path: string;
            /** Image Key */
            image_key: string;
            /** Image Source Id */
            image_source_id?: number | null;
            /** Image File */
            image_file?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ImageSchema */
        ImageSchema: {
            /** Id */
            id: number;
            /** Image Path */
            image_path: string;
            /** Image Key */
            image_key: string;
            source: components["schemas"]["ImageSourceSchema"] | null;
            /** Sha512 Hash */
            sha512_hash: string;
        };
        /** ImageSourceSchema */
        ImageSourceSchema: {
            /** Id */
            id: number;
            /** Source Name */
            source_name: string;
            /** Description */
            description: string | null;
        };
        /** PaginatedResults */
        PaginatedResults: {
            /** Items */
            items: components["schemas"]["SearchObjectSchema"][];
            /** Total */
            total: number;
        };
        /** SearchObjectSchema */
        SearchObjectSchema: {
            /** Id */
            id: number;
            /** Text Content */
            text_content: string;
            image: components["schemas"]["ImageSchema"] | null;
            /** Image Url */
            image_url?: string | null;
            /** Thumbnail Url */
            thumbnail_url?: string | null;
            /** Similarity Score */
            similarity_score?: number | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    search_api_search_get: {
        parameters: {
            query: {
                q: string;
                skip?: number;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedResults"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    admin_login_api_admin_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/x-www-form-urlencoded": components["schemas"]["Body_admin_login_api_admin_login_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_objects_api_admin_objects_get: {
        parameters: {
            query?: {
                skip?: number;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedResults"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_object_api_admin_objects_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_create_object_api_admin_objects_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchObjectSchema"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_object_api_admin_objects__object_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_update_object_api_admin_objects__object_id__put"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchObjectSchema"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_object_api_admin_objects__object_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_events_api_admin_events_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminEventSchema"][];
                };
            };
        };
    };
    resolve_event_api_admin_events__id__resolve_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_image_api_images__image_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                image_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_image_sources_api_admin_image_sources_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImageSourceSchema"][];
                };
            };
        };
    };
    get_thumbnail_api_images__image_id__thumbnail_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                image_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
