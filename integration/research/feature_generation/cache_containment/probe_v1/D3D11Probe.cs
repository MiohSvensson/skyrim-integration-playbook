using System;
using System.Runtime.InteropServices;
using System.Text;

internal static class D3D11Probe {
    [DllImport("d3d11.dll", CallingConvention = CallingConvention.StdCall)]
    private static extern int D3D11CreateDevice(IntPtr adapter, uint driverType, IntPtr software,
        uint flags, int[] featureLevels, uint featureLevelCount, uint sdkVersion,
        out IntPtr device, out int featureLevel, out IntPtr context);

    [DllImport("d3dcompiler_47.dll", CallingConvention = CallingConvention.StdCall)]
    private static extern int D3DCompile(byte[] data, UIntPtr size, string sourceName,
        IntPtr defines, IntPtr include, string entryPoint, string target,
        uint flags1, uint flags2, out IntPtr code, out IntPtr errors);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandleW(string name);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int CreateComputeShaderDelegate(IntPtr device, IntPtr bytecode,
        UIntPtr size, IntPtr classLinkage, out IntPtr shader);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate IntPtr GetBufferPointerDelegate(IntPtr blob);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate UIntPtr GetBufferSizeDelegate(IntPtr blob);

    private static int Run() {
        if (GetModuleHandleW("usvfs_x64.dll") == IntPtr.Zero) {
            Console.WriteLine("D3D11_PROBE_NO_USVFS");
            return 2;
        }
        Console.WriteLine("D3D11_PROBE_USVFS_PRESENT");
        string text = "RWTexture2D<float> output : register(u0); " +
            "[numthreads(1, 1, 1)] void main(uint3 id : SV_DispatchThreadID) " +
            "{ output[id.xy] = 0.731927; }";
        byte[] source = Encoding.ASCII.GetBytes(text);
        IntPtr device = IntPtr.Zero, context = IntPtr.Zero, code = IntPtr.Zero;
        IntPtr errors = IntPtr.Zero, shader = IntPtr.Zero;
        try {
            int hr = D3DCompile(source, new UIntPtr((uint)source.Length), "probe.hlsl",
                IntPtr.Zero, IntPtr.Zero, "main", "cs_5_0", 0, 0, out code, out errors);
            IntPtr blob = hr == 0 ? code : errors;
            if (blob == IntPtr.Zero) throw new InvalidOperationException("D3DCompile returned no blob");
            GetBufferPointerDelegate buffer = (GetBufferPointerDelegate)Marshal.GetDelegateForFunctionPointer(
                Marshal.ReadIntPtr(Marshal.ReadIntPtr(blob), 3 * IntPtr.Size), typeof(GetBufferPointerDelegate));
            if (hr != 0) {
                string message = errors == IntPtr.Zero ? "D3DCompile failed" : Marshal.PtrToStringAnsi(buffer(errors));
                throw new InvalidOperationException(message + " HRESULT=0x" + hr.ToString("X8"));
            }
            int[] levels = { 0xb000, 0xb100, 0xa100, 0xa000 };
            int level;
            hr = D3D11CreateDevice(IntPtr.Zero, 1, IntPtr.Zero, 0, levels, 4, 7,
                out device, out level, out context);
            if (hr != 0 || device == IntPtr.Zero) {
                throw new InvalidOperationException("Hardware D3D11CreateDevice failed HRESULT=0x" + hr.ToString("X8"));
            }
            IntPtr table = Marshal.ReadIntPtr(device);
            IntPtr method = Marshal.ReadIntPtr(table, 18 * IntPtr.Size);
            CreateComputeShaderDelegate create = (CreateComputeShaderDelegate)Marshal.GetDelegateForFunctionPointer(
                method, typeof(CreateComputeShaderDelegate));
            IntPtr bytecode = buffer(code);
            GetBufferSizeDelegate size = (GetBufferSizeDelegate)Marshal.GetDelegateForFunctionPointer(
                Marshal.ReadIntPtr(Marshal.ReadIntPtr(code), 4 * IntPtr.Size), typeof(GetBufferSizeDelegate));
            hr = create(device, bytecode, size(code), IntPtr.Zero, out shader);
            if (hr != 0 || shader == IntPtr.Zero) {
                throw new InvalidOperationException("CreateComputeShader failed HRESULT=0x" + hr.ToString("X8"));
            }
            Console.WriteLine("D3D11_HARDWARE_COMPUTE_SHADER_PASS");
            return 0;
        } finally {
            if (shader != IntPtr.Zero) Marshal.Release(shader);
            if (code != IntPtr.Zero) Marshal.Release(code);
            if (errors != IntPtr.Zero) Marshal.Release(errors);
            if (context != IntPtr.Zero) Marshal.Release(context);
            if (device != IntPtr.Zero) Marshal.Release(device);
        }
    }

    public static int Main() {
        try { return Run(); }
        catch (Exception error) {
            Console.WriteLine("D3D11_PROBE_FAIL|" + error.GetType().Name + "|" + error.Message);
            return 1;
        }
    }
}
