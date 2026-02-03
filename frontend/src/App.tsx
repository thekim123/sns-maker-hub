import { useEffect, useMemo, useState } from "react";
import type { StatusResponse } from "./types";

const formatTime = (value: string) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
};

const formatUptime = (seconds: number) => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}일 ${hours}시간`;
  if (hours > 0) return `${hours}시간 ${minutes}분`;
  return `${minutes}분`;
};

const emptyStatus: StatusResponse = {
  ok: false,
  server_time: "",
  uptime_seconds: 0,
  users: { registered: 0 },
  jobs: { queued: 0, processing: 0, done: 0, recent: [] },
  naver: { linked_accounts: 0 },
  latest_posts: []
};

export default function App() {
  const [status, setStatus] = useState<StatusResponse>(emptyStatus);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`API 오류: ${response.status}`);
        }
        const data = (await response.json()) as StatusResponse;
        if (active) {
          setStatus(data);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "알 수 없는 오류");
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    const timer = window.setInterval(load, 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const serverTime = useMemo(() => formatTime(status.server_time), [status.server_time]);

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">SNS Maker Hub</p>
          <h1>작업 큐와 게시 흐름을 한 눈에</h1>
          <p className="subtext">
            허브 상태, 작업 처리 현황, 네이버 게시 결과를 빠르게 확인하세요.
          </p>
        </div>
        <div className="hero-panel">
          <div>
            <span className="label">서버 시간</span>
            <strong>{serverTime || "-"}</strong>
          </div>
          <div>
            <span className="label">업타임</span>
            <strong>{formatUptime(status.uptime_seconds)}</strong>
          </div>
          <div>
            <span className="label">상태</span>
            <strong className={status.ok ? "ok" : "bad"}>
              {status.ok ? "정상" : "점검 필요"}
            </strong>
          </div>
        </div>
      </header>

      {error && (
        <section className="alert">
          <div>
            <h2>대시보드를 불러오지 못했습니다</h2>
            <p>{error}</p>
          </div>
          <button type="button" onClick={() => window.location.reload()}>
            다시 시도
          </button>
        </section>
      )}

      <section className="grid">
        <article className="card">
          <h3>대기 작업</h3>
          <p className="metric">{status.jobs.queued}</p>
          <p className="caption">큐에 남아 있는 작업</p>
        </article>
        <article className="card">
          <h3>처리 중</h3>
          <p className="metric">{status.jobs.processing}</p>
          <p className="caption">현재 진행 중인 작업</p>
        </article>
        <article className="card">
          <h3>완료됨</h3>
          <p className="metric">{status.jobs.done}</p>
          <p className="caption">완료된 작업 누계</p>
        </article>
        <article className="card">
          <h3>등록 사용자</h3>
          <p className="metric">{status.users.registered}</p>
          <p className="caption">허브 등록된 사용자</p>
        </article>
      </section>

      <section className="split">
        <article className="panel">
          <div className="panel-head">
            <h2>최근 작업</h2>
            <span className="badge">{status.jobs.recent.length}건</span>
          </div>
          {loading ? (
            <p className="muted">데이터를 불러오는 중…</p>
          ) : status.jobs.recent.length === 0 ? (
            <p className="muted">최근 작업 기록이 없습니다.</p>
          ) : (
            <ul className="list">
              {status.jobs.recent.map((job) => (
                <li key={job.job_id}>
                  <div>
                    <p className="primary">Job {job.job_id}</p>
                    <p className="secondary">User {job.user_id}</p>
                  </div>
                  <div className="meta">
                    <span>{job.status}</span>
                    <strong>{formatTime(job.updated_at)}</strong>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>최근 게시물</h2>
            <span className="badge">{status.latest_posts.length}건</span>
          </div>
          {loading ? (
            <p className="muted">데이터를 불러오는 중…</p>
          ) : status.latest_posts.length === 0 ? (
            <p className="muted">아직 생성된 글이 없습니다.</p>
          ) : (
            <ul className="list">
              {status.latest_posts.map((post) => (
                <li key={post.post_id}>
                  <div>
                    <p className="primary">{post.title}</p>
                    <p className="secondary">User {post.user_id}</p>
                  </div>
                  <div className="meta">
                    <span>생성</span>
                    <strong>{formatTime(post.created_at)}</strong>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>

      <section className="cta">
        <div>
          <h2>허브가 안정적으로 돌고 있어요</h2>
          <p>
            ALB + ACM 구성 후에도 이 화면에서 큐와 게시 상태를 바로 확인할 수 있습니다.
          </p>
        </div>
        <div className="cta-actions">
          <button type="button" onClick={() => window.location.reload()}>
            새로고침
          </button>
          <a href="/health" className="ghost">
            헬스체크 확인
          </a>
        </div>
      </section>
    </div>
  );
}
