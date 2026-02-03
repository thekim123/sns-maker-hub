export type StatusResponse = {
  ok: boolean;
  server_time: string;
  uptime_seconds: number;
  users: {
    registered: number;
  };
  jobs: {
    queued: number;
    processing: number;
    done: number;
    recent: Array<{
      job_id: string;
      user_id: string;
      status: string;
      updated_at: string;
    }>;
  };
  naver: {
    linked_accounts: number;
  };
  latest_posts: Array<{
    post_id: string;
    user_id: string;
    title: string;
    created_at: string;
  }>;
};
