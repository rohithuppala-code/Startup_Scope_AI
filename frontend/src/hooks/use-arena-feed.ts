"use client";
import { useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";

interface Post {
  id: string;
  title: string;
  content: string;
  author_id: string;
  author_username: string;
  karma_score: number;
  upvote_count: number;
  downvote_count: number;
  comment_count: number;
  tags: string[];
  created_at: string;
  report_json?: Record<string, unknown> | null;
  validation_id?: string | null;
}

interface UseArenaFeedReturn {
  posts: Post[];
  loading: boolean;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refreshFeed: () => Promise<void>;
  updatePost: (postId: string, updates: Partial<Post>) => void;
  prependPost: (post: Post) => void;
}

export function useArenaFeed(pageSize = 20): UseArenaFeedReturn {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const pageRef = useRef(1);
  const initialLoadDone = useRef(false);
  const loadingRef = useRef(false);

  const fetchPage = useCallback(
    async (page: number, replace = false) => {
      loadingRef.current = true;
      setLoading(true);
      try {
        const data = await api<Post[]>(
          `/api/v1/arena/posts?page=${page}&page_size=${pageSize}&sort_by=recent`
        );
        if (replace) {
          setPosts(data);
        } else {
          setPosts((prev) => [...prev, ...data]);
        }
        setHasMore(data.length === pageSize);
      } catch (err) {
        console.error("[ArenaFeed] fetch error:", err);
        setHasMore(false);
      } finally {
        setLoading(false);
        loadingRef.current = false;
      }
    },
    [pageSize]
  );

  const loadMore = useCallback(async () => {
    if (loadingRef.current || !hasMore) return;
    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      pageRef.current = 1;
      await fetchPage(1, true);
    } else {
      pageRef.current += 1;
      await fetchPage(pageRef.current);
    }
  }, [fetchPage, hasMore]);

  const refreshFeed = useCallback(async () => {
    pageRef.current = 1;
    initialLoadDone.current = true;
    await fetchPage(1, true);
  }, [fetchPage]);

  const updatePost = useCallback((postId: string, updates: Partial<Post>) => {
    setPosts((prev) =>
      prev.map((p) => (p.id === postId ? { ...p, ...updates } : p))
    );
  }, []);

  const prependPost = useCallback((post: Post) => {
    setPosts((prev) => [post, ...prev]);
  }, []);

  return { posts, loading, hasMore, loadMore, refreshFeed, updatePost, prependPost };
}
