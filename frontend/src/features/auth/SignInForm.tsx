import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { useAuth } from './AuthProvider'

const credentialsSchema = z.object({
  email: z.string().trim().email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
})

type Credentials = z.infer<typeof credentialsSchema>

export function SignInForm({ emailLabel = 'Work email' }: { emailLabel?: string }) {
  const { signIn } = useAuth()
  const [requestError, setRequestError] = useState('')
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Credentials>({
    resolver: zodResolver(credentialsSchema),
  })

  const submit = async ({ email, password }: Credentials) => {
    setRequestError('')
    try {
      await signIn(email, password)
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Sign-in failed. Try again.')
    }
  }

  return (
    <form className="sign-in-form" onSubmit={handleSubmit(submit)} noValidate>
      <div className="form-field">
        <Label htmlFor="email">{emailLabel}</Label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoCapitalize="none"
          inputMode="email"
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? 'email-error' : undefined}
          {...register('email')}
        />
        {errors.email && <p className="field-error" id="email-error">{errors.email.message}</p>}
      </div>
      <div className="form-field">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={Boolean(errors.password)}
          aria-describedby={errors.password ? 'password-error' : undefined}
          {...register('password')}
        />
        {errors.password && <p className="field-error" id="password-error">{errors.password.message}</p>}
      </div>
      {requestError && <p className="form-error" role="alert">{requestError}</p>}
      <Button className="sign-in-button" type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Checking credentials…' : 'Sign in'}
      </Button>
    </form>
  )
}
