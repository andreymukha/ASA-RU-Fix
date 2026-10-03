namespace AsaRuFix.Core;

// A Mutex must be released by the thread that acquired it, even across asynchronous operations.
public sealed class UserMutex : IDisposable
{
    private readonly ManualResetEventSlim release = new(false);
    private readonly Thread owner;
    private bool disposed;

    private UserMutex(string name, TimeSpan timeout, TaskCompletionSource<bool> ready)
    {
        owner = new Thread(() =>
        {
            try
            {
                using var mutex = new Mutex(false, name);
                bool acquired;
                try { acquired = mutex.WaitOne(timeout); }
                catch (AbandonedMutexException) { acquired = true; }
                ready.TrySetResult(acquired);
                if (!acquired) return;
                try { release.Wait(); }
                finally { mutex.ReleaseMutex(); }
            }
            catch (Exception error) { ready.TrySetException(error); }
        }) { IsBackground = true, Name = "ASA-RU-Fix mutex owner" };
        owner.Start();
    }

    public static UserMutex? TryAcquire(string name, TimeSpan timeout)
    {
        var ready = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var lease = new UserMutex(name, timeout, ready);
        try
        {
            if (ready.Task.GetAwaiter().GetResult()) return lease;
            lease.Dispose();
            return null;
        }
        catch { lease.Dispose(); throw; }
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        release.Set();
        owner.Join();
        release.Dispose();
    }
}
