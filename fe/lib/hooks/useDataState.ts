import { UseQueryResult } from '@tanstack/react-query';

export function useDataState<TData>(
  queryResult: UseQueryResult<TData>,
  isEmptyFn?: (data: TData | undefined) => boolean
) {
  const { data, isLoading, isError, error } = queryResult;
  
  const isEmpty = !isLoading && !isError && (isEmptyFn ? isEmptyFn(data) : !data);
  
  return { data, isLoading, isEmpty, isError, error };
}