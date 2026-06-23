## Style Conventions

- Start by applying normal StyleCop rules. The standard StyleCop rules have been enabled on the branch. Enable this in your project file with `<EnableStyleCopAnalyzer>true</EnableStyleCopAnalyzer>`.
- You should have XML comments for all non-private members.
- You may ignore ordering rules for public/internal/protected/private.
- You should ignore rules that specify which text should go into XML documentation (Comments like "Initializes a new instance of the MyClass class" are a waste of space).
- You should use complete sentences in all comments.
- You should have methods with no more than 5 arguments.
- Local variables must be referred to with `this.`, e.g., `this.myField`.
- Static variables should be referred to via the name of the class. e.g., `MyClassName.StaticProperty`.

Note: This list should be replaced by a StyleCop.settings file.

## Naming Conventions

- One data type definition per file. File name must match type name. (Nested types are acceptable, but they should be used only with
the parent class.)
- No encoding type information into symbol names
    - No [Hungarian notation](https://msdn.microsoft.com/library/aa260976(v=vs.60).aspx) whatsoever.
- No underscores whatsoever. (Possible exception is for UI elements in a MVC project.)
- All symbol names should contain whole words only. Only well-known acronyms (e.g., TCP, DNS, URL) may be abbreviated.
    - Local variables, function parameters, and private fields should use camelCasing.
    - Types, methods, properties, public fields (where acceptable), and public constants should use PascalCasing
    - private fields should use camelCasing.

### Advanced Naming Conventions

When naming a symbol, choose a part of speech that matches the syntax of how the symbol is used.
This makes the code read more like a natural language, which helps readability and reduces errors, because humans
are already adept at matching syntax and semantics in natural languages.

- Non-Boolean fields, variables, and properties should be noun phrases:
    - `TimeSpan duration;`
    - `int retryCount;`
- Classes and structs should be singular noun phrases
    - `struct TimeSpan`;
    - `class WidgetCollection`;
    - NOT: `class Widgets` (because what's a Widgets?)
- Non-boolean methods should be present-tense imperative verb phrases:
    - `Enable();`
    - `ValidateAgainst(T x);`
    - `DoWork();`
- Boolean fields, methods, and properties should be declarative statements:
    - `bool hasErrors;`
    - `bool IsValid{get;}`
    - `bool ShouldProcess(T x);`
- Avoid abbreviations that may only be familiar to a small set of people.

## Exceptions

Never throw or catch the base `Exception` type. The only exception to this is for handling errors thrown by components
which we don't control, such as partner plugins. These places should be rare and well-documented.

## Performance Consideration

### Memory

Memory use can have one of the greatest impacts on performance due to GC effects, thus any use of memory needs
to be carefully considered. We consider memory in three ways: Lifetime, Kind, and Volume. I.e., for all memory allocated
how long will it live, what kind of memory is allocated (byte array, memory stream, string builder, etc.), and how much
of it is being allocated.

In addition to the resources above, see these places for more GC background:

- [Fundamentals of Garbage Collection](https://docs.microsoft.com/dotnet/standard/garbage-collection/fundamentals)
- [Maoni's Weblog - CLR Garbage Collector](https://blogs.msdn.microsoft.com/maoni/)

#### Lifetime

Categorize the memory usage on your service and make sure all memory allocated should have a lifetime that lines up with
one of these categories. If it doesn't, it's a red-flag and we should look closely to see if it is correct.
For instance, if memory is allocated during an API request execution but that has
process lifetime then we need to consider whether that's really necessary, what bounds its growth request after request, etc.

Assuming the lifetime of the memory does properly line up with one of those categories, is it lined up with the right
one? I.e., is someone allocating per-request memory that really ought to be per-process?

The ApplicationHost makes heavy use of tasks: within the graph execution engine, the request/response processing, within all
platform I/O plugins, etc. Any memory that lives across an "async break", even if it is per-plugin memory, has the
potential to survive a Gen 0 GC. Thus, such memory should be kept to a minimum. Consider not only the memory
explicitly allocated at the start of a task and consumed at the end, but also the implicit memory created for
things like lambda closures, etc.

Should the memory be pooled? This is typically a consideration for per-request memory, since it is most likely to
have mid-life crisis, but may be a consideration for per-plugin memory for async plugins.

- `RecyclableMemoryStream` exists for pooling `byte` buffers
- `ObjectPool` is available for general-purpose pooling.

#### Kind

In general when we think of the "kind" of the memory we are looking for memory that may be a large object, which ends up
on the LOH and causes direct Gen 2 pressure. The easiest here is memory streams: in general our `RecyclableMemoryStream`
pool should be used, and the stream must be returned to the pool before the query ends.

For other types that have the potential to be large objects, like `byte[]`, `StringBuilder`, even collections
like lists and dictionaries, is the size determined by something that could be large on some queries, like data
returned from a store or coming in over the wire? If so, what mitigation is there for the case where
this per-query data is large?

Finalizable objects should be rare, and any such objects should be reviewed carefully to determine why they need
finalization semantics. These are guaranteed Gen 1 pressure.

#### Volume

Look at the volume of memory allocated closely. Allocating a bunch of small objects for every plugin execution may
be nice because it makes small garbage, and thus is easily cleaned up by a Gen 0, but not allocating is even nicer.
If there's a lot of temporary garbage, why? Can it be reduced to help reduce our Gen 0 pressure? Conversely,
allocating too much temporary memory in Gen 0 can be problematic if it puts us close to allocating an entire memory
segment within a query, which guarantees an expensive GC.

Collections that have a lot of entries may end up harboring large objects within their implementation. Think
about `Dictionary<K,V>`: what's that made up of inside? A couple of arrays to hold the values, and even if they
are made up of refs those arrays may become large objects and thus a concern if they are per-query
or per-plugin.

#### Issues we've Seen

- Gen2 memory pressure. Large memory allocations are automatically in Gen2, which will increase number of expensive Gen2
collections. Typical violation of this is tied to incorrect use of (or lack of use of) `RecyclableMemoryStream`
    - Calling `ToArray()` on a `MemoryStream`, especially a `RecyclableMemoryStream` is almost never correct. In general,
making copies of bytes, converting a pooled buffer to an unpooled one, should be avoided at all cost.
- Gen0 times. In general, this is tied to our allocation rate and pattern, but we've had exotic problems with pinning
caused by .NET's `FileSystemWatcher` class. We should be deeply skeptical of any per-query memory allocation.
- High memory use. Some features are prone to high memory use. The cost needs to be understood and evaluated on a
case-by-case basis. Here are known areas prone to high memory usage:
    - `RuntimePlugin` - There are a lot of these in memory. Any addition to these can have a large effect.
    - AP Perf Counters - These can take a few hundred MB. Every new counter is multiplied across all its instances.
    - `RecyclableMemoryStream`
    - Wordbreakers - These consume a few hundred MB of native memory. They do not contribute to the managed (GC) heap.

### Tasks

Much of the ApplicationHost library uses Tasks and the Task Parallel Library to control execution. TPL is a rich library
with a lot of really fun and interesting features, most of which we do not use. We want to keep it that way. We tend to
use a very simple, common pattern for Tasks within the ApplicationHost library and any deviation from that is a red-flag
that should be questioned carefully. The pattern is:

1. On the start of an async task:
    1. Create a `TaskCompletionSource tcs`.
    2. Kick off some async work, passing the tcs and any other interesting data to a continuation function.
    3. Optionally add more continuations to the pending task, as with `tcs.Task.ContinueWith()`.
    4. Return `tcs.Task`.
2. On the far side of the async break:
    1. Gather up the result, and use `tcs.TrySetResult()` to complete the task and convey the result.
    2. A task's exception property is also observed and logged if necessary.

It's common and reasonable to call a function which returns a Task and to call `ContinueWith()` on that task to add more
work to be done on completion. This may be done "normally", where the continuation runs no matter what the result of the
task, or it may be done with the variants of `ContinueWith()` that cause the continuation to only run on errors or
success as appropriate.

Any explicit waiting on a task is a red-flag. We don't want to block thread pool threads at all, as it encourages the
thread pool to inject more and oversubscribe the machine.

Watch out for implicit waiting, i.e., Task.Result may block if the task is not yet complete.

We do not yet have specific guidance around task continuations that are explicitly synchronous vs. asynchronous. For now
we say that any specification of a synchronous continuation is a red-flag and should be looked at closely.

For more background on TPL read:

- [TPL in Microsoft docs](https://docs.microsoft.com/dotnet/standard/parallel-programming/task-parallel-library-tpl)
- Steven Toub's excellent whitepaper [Task-based Asynchronous Pattern](https://www.microsoft.com/download/details.aspx?id=19957).

### Locks

Some library is inherently multi-threaded, and there are many places where synchronization over shared data
is required. However, these should be kept to a minimum, and be as simple as possible.

The mantra for locking should "Simplicity is king."

Thus, all synchronization should be simple `lock(foo) { }` and nothing more, with every
variable protected by the same lock instance every time. The work done under a lock should be minimal, and ideally
measured in a handful of statements.

Any code that gets even remotely creative with locking is a red-flag and needs to be studied carefully. If it remains, it
must be commented thoroughly. This includes deceptively simple patterns like the classic Double Checked Locking (DCL) pattern
and things like `InterlockedIncrement()`. Any code involving custom locking or use of `InterlockedCompareExchange()`
is a massive red-flag and requires solid proof via measurement of its value.

Reader/Writer locks are also a red-flag. They're typically unnecessary and slower than a normal lock for the common cases
within the ApplicationHost library. In fact, today, no code in the ApplicationHost library uses a reader/writer lock.

.Net 4 provides a bunch of really nice concurrent collections that look fun and easy to use. However, there are
frequently mistakes with these as people confuse individual small atomic operations with a larger consistency guarantee
that simply does not exist. Any code that looks something up in a concurrent collection, then makes some decision
resulting in a change to the collection is likely wrong, and likely fails to account for other concurrent changes. In
these cases it's almost always more correct to have a normal collection and a normal lock. Consider all uses of
concurrent collections suspicious and review carefully.

### General Badness

There are some common managed constructs that are performance problems. Some examples we've seen creep into our codebase
are:

1. Reflection – typically slow, at a minimum, and can be used for evil by circumventing normal member visibility rules
and creating brittle, non-obvious dependencies between components.
2. Stupid String Tricks – the classics, like appending in a loop, using ToLower() instead of a case-insensitive
comparer, using Split() like it's going out of style, etc.

In general, you should know what each .NET API (or any other library) that you use does under the hood with reasonably
high confidence. When in doubt, use [dotPeek](https://www.jetbrains.com/decompiler/) or [ILSpy](https://ilspy.net/) to
make sure you understand what you are using at a deep level.

### Specific Issues

- `Enum.HasFlag()`, `Enum.ToString()`, etc. all have very heavy implementations and are to be avoided if possible (use `&`
instead of `HasFlag`).
- `System.Process` class will cause a large object allocation and should be avoided.
- `FileSystemWatcher` will pin objects. This has been shown to cause a severe GC problem.

### Events & Boxing

Anything that is written to events (including `LogAssert`) must already exist as an object. Boxing or string conversion
is not allowed to happen. This is because we don't want to waste time creating objects for events that may rarely (or
never, for asserts) be written. This means sometimes adding a condition check before the event call to ensure you
will actually need to make it.

An example for avoiding boxing:

Bad code:

```csharp
    LogAssert.Assert(targetNode != null, "Null nodes! Something broke in workflow {0} at index {1}",
                     this.Workflow.Alias, otd.TargetPluginIndex);
```

Good code:

```csharp
    if (targetNode == null)
    {
        // We put this inside an if to avoid boxing of the int in the args.
        LogAssert.Assert(false, "Null nodes! Something broke in workflow {0} at index {1}",
                         this.Workflow.Alias, otd.TargetPluginIndex);
    }
```

An example of checking if a verbose event is enabled before creating an expensive string:

Bad code:

```csharp
    Events.Write.HttpRequestReceived(context.Request.Url.ToString());
```

Good code:

```csharp
    // We check if the event is enable in the first place because Url.ToString
    //isn't cheap -- boxing + string formatting
    if (Events.Write.IsEnabled(EventLevel.Verbose, Events.Keywords.General))
    {
        Events.Write.HttpRequestReceived(context.Request.Url.ToString());
    }
```

### Branch Naming Conventions
Branches pushed to VSTS must use one of the following conventions:

1. Developer - dev/$env:username/LOCAL_REF_SIMPLIFIED
   For sharing changes across devices or with co-workers.

     git branch -m LOCAL_REF_SIMPLIFIED dev/$env:username/LOCAL_REF_SIMPLIFIED
     git push --set-upstream origin dev/$env:username/LOCAL_REF_SIMPLIFIED

2. Feature - feature/<feature name>/LOCAL_REF_SIMPLIFIED
   For long-term features that continue to exist even after completed PR.
   <feature name> needs to be described in $env:REPOROOT\.config\branches\feature.csv
   Feature branches are fetched by default, to configure see https://aka.ms/LimitFetchedBranches

     git branch -m LOCAL_REF_SIMPLIFIED feature/<feature name>/LOCAL_REF_SIMPLIFIED
     git push --set-upstream origin feature/<feature name>/LOCAL_REF_SIMPLIFIED

3. Release - release/<release name>/LOCAL_REF_SIMPLIFIED
   For long-term releases that continue to exist even after completed PR.
   <release name> needs to be described in $env:REPOROOT\.config\branches\release.csv
   Release branches are NOT fetched by default, to configure see https://aka.ms/LimitFetchedBranches

     git branch -m LOCAL_REF_SIMPLIFIED release/<release name>/LOCAL_REF_SIMPLIFIED
     git push --set-upstream origin release/<release name>/LOCAL_REF_SIMPLIFIED

4. Custom - any branch name allowed in $env:REPOROOT\.config\branches\IncludeOnFetch.txt
   Used only for verified compatibility issues with the build system.
   This is not an option for a regular development model.

All branch names need to use lowercase since accidental
mixing of upper and lowercase is known to cause problems.