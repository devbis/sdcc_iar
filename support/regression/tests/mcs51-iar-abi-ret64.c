#ifdef __SDCC_mcs51
unsigned long long
callee_u64_void(void) __iar
{
  return 0x1122334455667788ull;
}

unsigned long long
caller_u64_void(void)
{
  return callee_u64_void();
}

unsigned long long
callee_u64_float(float f) __iar
{
  return (unsigned long long)f;
}

unsigned long long
caller_u64_float(float f)
{
  return callee_u64_float(f);
}
#endif
